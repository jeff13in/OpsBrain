"""User-scoped Supabase HTTP calls with no shared mutable SDK auth state."""

from datetime import UTC, datetime
from uuid import UUID

import httpx

from orchestrator.auth.flows import Throttled
from orchestrator.auth.sessions import (
    InvalidIdentity,
    PersistenceError,
    ProviderUnavailable,
    WorkspaceUnavailable,
)


class SupabaseProvider:
    def __init__(self, origin, publishable_key, *, transport=None):
        self.origin = origin.rstrip('/')
        self._key = publishable_key
        self._transport = transport

    def _request(self, method, path, *, access=None, payload=None):
        headers = {'apikey': self._key}
        if access:
            headers['Authorization'] = 'Bearer ' + access
        try:
            with httpx.Client(timeout=5, follow_redirects=False, transport=self._transport) as client:
                response = client.request(method, self.origin + path, headers=headers, json=payload)
            if response.status_code == 429:
                raise Throttled()
            if response.status_code in (400, 401, 403, 422):
                raise InvalidIdentity()
            if response.status_code not in (200, 201, 204) or len(response.content) > 65536:
                raise ProviderUnavailable()
            return response.json() if response.content else None
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable() from exc

    def verified_user(self, access):
        body = self._request('GET', '/auth/v1/user', access=access)
        try:
            if not body.get('email_confirmed_at') or body.get('is_anonymous') or body.get('deleted_at'):
                raise InvalidIdentity()
            if body.get('banned_until'):
                banned_until = datetime.fromisoformat(body['banned_until'])
                if banned_until.tzinfo is None or banned_until > datetime.now(UTC):
                    raise InvalidIdentity()
            return str(UUID(body['id']))
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise InvalidIdentity() from exc

    def workspaces(self, access):
        body = self._request('GET', '/rest/v1/workspaces?select=id&order=created_at.asc&limit=100', access=access)
        try:
            if not isinstance(body, list) or len(body) > 100:
                raise ProviderUnavailable()
            return tuple(str(UUID(row['id'])) for row in body)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderUnavailable() from exc

    def refresh(self, refresh_token):
        body = self._request('POST', '/auth/v1/token?grant_type=refresh_token', payload={'refresh_token': refresh_token})
        return self.token_pair(body)

    @staticmethod
    def token_pair(body):
        try:
            access, refresh, expires = body['access_token'], body['refresh_token'], body['expires_in']
            if not isinstance(access, str) or not isinstance(refresh, str) or not access or not refresh:
                raise ProviderUnavailable()
            if type(expires) is not int or not 0 < expires <= 86400:
                raise ProviderUnavailable()
            return access, refresh, expires
        except (KeyError, TypeError) as exc:
            raise ProviderUnavailable() from exc

    def login(self, email, password):
        return self.token_pair(self._request('POST', '/auth/v1/token?grant_type=password', payload={'email': email, 'password': password}))

    def signup(self, email, password, callback):
        from urllib.parse import urlencode
        self._request('POST', '/auth/v1/signup?' + urlencode({'redirect_to': callback}), payload={'email': email, 'password': password})

    def resend(self, email, callback):
        from urllib.parse import urlencode
        self._request('POST', '/auth/v1/resend?' + urlencode({'redirect_to': callback}), payload={'type': 'signup', 'email': email})

    def recover(self, email, callback):
        from urllib.parse import urlencode
        self._request('POST', '/auth/v1/recover?' + urlencode({'redirect_to': callback}), payload={'email': email})

    def verify(self, token_hash, kind):
        return self.token_pair(self._request('POST', '/auth/v1/verify', payload={'token_hash': token_hash, 'type': kind}))

    def exchange_code(self, auth_code, code_verifier):
        return self.token_pair(self._request('POST', '/auth/v1/token?grant_type=pkce',
                                             payload={'auth_code': auth_code, 'code_verifier': code_verifier}))

    def password(self, access, password):
        self._request('PUT', '/auth/v1/user', access=access, payload={'password': password})

    def logout_all(self, access):
        self._request('POST', '/auth/v1/logout?scope=global', access=access)

    def provision(self, access):
        # Subject comes from the verified user JWT; the RPC accepts no target ID.
        self.verified_user(access)
        body = self._data_request('POST', '/rest/v1/rpc/ensure_personal_workspace', access, {})
        try:
            return str(UUID(body))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ProviderUnavailable() from exc

    def logout(self, access):
        self._request('POST', '/auth/v1/logout?scope=local', access=access)

    def workspace_summary(self, access, user_id, workspace_id):
        user_id, workspace_id = str(UUID(user_id)), str(UUID(workspace_id))
        workspaces = self._request('GET', f'/rest/v1/workspaces?select=id,name&id=eq.{workspace_id}&limit=1', access=access)
        if not isinstance(workspaces, list) or len(workspaces) != 1:
            raise WorkspaceUnavailable()
        profiles = self._request('GET', f'/rest/v1/profiles?select=user_id,display_name,preferences,version&user_id=eq.{user_id}&limit=1', access=access)
        projects = self._request('GET', '/rest/v1/projects?select=id,workspace_id,title,updated_at,version'
                                 f'&workspace_id=eq.{workspace_id}&order=updated_at.desc,id.asc&limit=10', access=access)
        try:
            workspace = workspaces[0]
            if str(UUID(workspace['id'])) != workspace_id or not isinstance(workspace['name'], str) or not 0 < len(workspace['name'].strip()) <= 120:
                raise ProviderUnavailable()
            if not isinstance(profiles, list) or len(profiles) > 1:
                raise ProviderUnavailable()
            profile = profiles[0] if profiles else {'user_id': user_id, 'display_name': ''}
            if str(UUID(profile['user_id'])) != user_id or not isinstance(profile['display_name'], str) or len(profile['display_name']) > 120:
                raise ProviderUnavailable()
            if not isinstance(projects, list) or len(projects) > 10:
                raise ProviderUnavailable()
            recent = []
            for project in projects:
                if (str(UUID(project['workspace_id'])) != workspace_id or not isinstance(project['title'], str)
                    or not 0 < len(project['title'].strip()) <= 200 or type(project['version']) is not int
                    or not 0 < project['version'] <= 9007199254740991):
                    raise ProviderUnavailable()
                updated = datetime.fromisoformat(project['updated_at'])
                if updated.tzinfo is None:
                    raise ProviderUnavailable()
                recent.append({'id': str(UUID(project['id'])), 'title': project['title'],
                               'updated_at': updated.isoformat(), 'version': project['version']})
            persistence = type(profile.get('version')) is int and isinstance(profile.get('preferences'), dict)
            return {'workspace': {'id': workspace_id, 'name': workspace['name']},
                    'profile': {key: profile[key] for key in ('display_name','preferences','version') if key in profile}, 'recent_projects': recent,
                    'capabilities': {'project_writes': persistence, 'preferences': persistence, 'saved_work': persistence, 'activity': False, 'live_tools': False}}
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderUnavailable() from exc

    def _data_request(self, method, path, access, payload=None):
        try:
            with httpx.Client(timeout=5, follow_redirects=False, transport=self._transport) as client:
                response = client.request(method, self.origin + path, headers={'apikey': self._key, 'Authorization': 'Bearer ' + access}, json=payload)
            if len(response.content) > 262144:
                raise ProviderUnavailable()
            if response.status_code == 401:
                raise InvalidIdentity()
            if response.status_code not in (200, 201):
                try:
                    code = response.json().get('code')
                except (ValueError, AttributeError):
                    code = None
                status = {'40001':409,'23505':409,'P0002':404,'42501':403,'23514':422,'23503':422,'22023':422,'54000':429}.get(code,503)
                raise PersistenceError(status)
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable() from exc

    def list_records(self, access, user_id, workspace_id, kind, cursor, limit):
        fields = 'id,workspace_id,title,updated_at,version' + (',project_id,owner_id' if kind == 'saved_work' else ',creator_id')
        path = f'/rest/v1/{kind}?select={fields}&workspace_id=eq.{workspace_id}&order=id.asc&limit={limit+1}'
        if cursor:
            path += f'&id=gt.{UUID(cursor)}'
        rows = self._data_request('GET', path, access)
        if not isinstance(rows,list) or len(rows)>limit+1:
            raise ProviderUnavailable()
        for row in rows:
            if row.get('workspace_id')!=workspace_id or row.get('owner_id',row.get('creator_id'))!=user_id:
                raise ProviderUnavailable()
        return {'records':rows[:limit],'next_cursor':rows[limit-1]['id'] if len(rows)>limit else None}

    def read_record(self, access, user_id, workspace_id, kind, record_id):
        fields = 'id,workspace_id,title,updated_at,version' + (',project_id,owner_id,payload' if kind == 'saved_work' else ',creator_id')
        page = self._data_request('GET', f'/rest/v1/{kind}?select={fields}&workspace_id=eq.{workspace_id}&id=eq.{UUID(record_id)}&limit=1', access)
        if not isinstance(page,list) or len(page)!=1:
            raise WorkspaceUnavailable()
        row=page[0]
        if row.get('workspace_id')!=workspace_id or row.get('owner_id',row.get('creator_id'))!=user_id:
            raise WorkspaceUnavailable()
        return row

    def mutate(self, access, user_id, workspace_id, request_id, operation, record_id, version, changes):
        return self._data_request('POST','/rest/v1/rpc/workspace_mutate',access,
          {'request_id':request_id,'target_workspace':workspace_id,'operation':operation,
           'record_id':user_id if operation=='profile.update' else record_id,'expected_version':version,'changes':changes})
