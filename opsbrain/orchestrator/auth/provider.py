"""User-scoped Supabase HTTP calls with no shared mutable SDK auth state."""

from datetime import UTC, datetime
from uuid import UUID

import httpx

from orchestrator.auth.sessions import InvalidIdentity, ProviderUnavailable


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
            if response.status_code in (400, 401, 403):
                raise InvalidIdentity()
            if response.status_code not in (200, 204) or len(response.content) > 65536:
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
        try:
            access, refresh, expires = body['access_token'], body['refresh_token'], body['expires_in']
            if not isinstance(access, str) or not isinstance(refresh, str) or not access or not refresh:
                raise ProviderUnavailable()
            if type(expires) is not int or not 0 < expires <= 86400:
                raise ProviderUnavailable()
            return access, refresh, expires
        except (KeyError, TypeError) as exc:
            raise ProviderUnavailable() from exc

    def logout(self, access):
        self._request('POST', '/auth/v1/logout?scope=local', access=access)
