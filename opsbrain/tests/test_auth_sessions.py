"""Session boundary tests; provider and transactional store are controlled fixtures."""

import copy
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import UUID

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from orchestrator.auth.persistence import SavedPayload
from orchestrator.auth.persistence import router as persistence_router
from orchestrator.auth.provider import SupabaseProvider
from orchestrator.auth.routes import get_boundary, router, set_session_cookie
from orchestrator.auth.sessions import (
    InvalidIdentity,
    PostgresSessionStore,
    ProviderUnavailable,
    SessionManager,
)
from orchestrator.auth.settings import AuthSettings

USER = '00000000-0000-4000-8000-000000000001'
WORKSPACE = '00000000-0000-4000-8000-000000000002'
OTHER = '00000000-0000-4000-8000-000000000003'


class StoreFixture:
    def __init__(self):
        self.rows = {}
        self.lock = threading.RLock()

    def insert(self, record):
        self.rows[record.session_hash] = copy.deepcopy(record)

    @contextmanager
    def locked(self, key):
        with self.lock:
            slot = [copy.deepcopy(self.rows.get(key))]
            yield slot
            if slot[0] is None:
                self.rows.pop(key, None)
            else:
                self.rows[key] = slot[0]


class ProviderFixture:
    user = USER
    workspace_ids = (WORKSPACE,)
    refresh_count = 0
    fail = None
    logout_count = 0

    def verified_user(self, access):
        if self.fail:
            raise self.fail()
        return self.user

    def workspaces(self, access):
        return self.workspace_ids

    def refresh(self, refresh):
        if self.fail:
            raise self.fail()
        self.refresh_count += 1
        return 'refreshed-access', 'rotated-refresh', 3600

    def logout(self, access):
        self.logout_count += 1
        if self.fail:
            raise self.fail()

    def workspace_summary(self, access, user_id, workspace_id):
        return {'workspace': {'id': workspace_id, 'name': 'My workspace'},
                'profile': {'display_name': 'Client A'}, 'recent_projects': [],
                'capabilities': {'project_writes': False, 'preferences': False, 'activity': False, 'live_tools': False}}

    def mutate(self, access, user_id, workspace_id, request_id, operation, record_id, version, changes):
        self.last_mutation=(user_id,workspace_id,operation,record_id,changes)
        return {'id':user_id if operation=='profile.update' else record_id,'version':version+1,'deleted':operation.endswith('.delete')}


@pytest.fixture
def setup():
    store, provider, now = StoreFixture(), ProviderFixture(), [1000]
    key = Fernet.generate_key()
    manager = SessionManager(store, provider, key, clock=lambda: now[0])
    cookie, principal = manager.issue('secret-access', 'secret-refresh', 3600)
    return manager, store, provider, now, key, cookie, principal


def test_cookie_and_tokens_are_not_plaintext_in_records(setup):
    manager, store, _, _, _, cookie, _ = setup
    record = store.rows[manager.cookie_hash(cookie)]
    assert cookie not in repr(record)
    assert 'secret-access' not in repr(record)
    assert 'secret-refresh' not in record.token_ciphertext
    assert manager.authenticate(cookie).user_id == USER
    assert manager.authenticate('forged') is None
    assert manager.authenticate(None) is None


def test_manager_restart_preserves_session_and_csrf(setup):
    manager, store, provider, now, key, cookie, _ = setup
    restarted = SessionManager(store, provider, key, clock=lambda: now[0])
    assert restarted.authenticate(cookie).workspace_ids == (WORKSPACE,)
    assert restarted.csrf_token(cookie) == manager.csrf_token(cookie)
    assert restarted.csrf_token(cookie) != restarted.csrf_token('z' * 43)


def test_postgres_driver_uuid_rows_match_verified_provider_identity(setup, monkeypatch):
    manager, store, provider, now, key, cookie, _ = setup
    row = copy.deepcopy(vars(store.rows[manager.cookie_hash(cookie)]))
    row['user_id'] = UUID(row['user_id'])  # psycopg returns UUID objects.
    queries = []
    class ConnectionFixture:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, sql, params=None):
            queries.append((sql, params))
            return self
        def fetchone(self):
            return row
    monkeypatch.setattr('psycopg.connect', lambda *args, **kwargs: ConnectionFixture())
    postgres = PostgresSessionStore('synthetic-test-dsn')
    replica = SessionManager(postgres, provider, key, clock=lambda: now[0])
    assert replica.authenticate(cookie).user_id == USER
    assert any('for update' in sql for sql, _ in queries)
    assert any(sql.startswith('update opsbrain_private.app_sessions') for sql, _ in queries)


@pytest.mark.parametrize('elapsed', [86400, 604800])
def test_expiration_removes_session(setup, elapsed):
    manager, store, _, now, _, cookie, _ = setup
    now[0] += elapsed
    assert manager.authenticate(cookie) is None
    assert not store.rows


def test_ciphertext_tampering_fails_closed(setup):
    manager, store, _, _, _, cookie, _ = setup
    store.rows[manager.cookie_hash(cookie)].token_ciphertext = 'tampered'
    assert manager.authenticate(cookie) is None
    assert not store.rows


def test_ciphertext_cannot_be_moved_between_session_rows(setup):
    manager, store, _, _, _, cookie, _ = setup
    other_cookie, _ = manager.issue('access-2', 'refresh-2', 3600)
    store.rows[manager.cookie_hash(other_cookie)].token_ciphertext = store.rows[manager.cookie_hash(cookie)].token_ciphertext
    assert manager.authenticate(other_cookie) is None
    assert manager.authenticate(cookie) is not None


def test_provider_identity_switch_or_removed_workspace_revokes_session(setup):
    manager, store, provider, _, _, cookie, _ = setup
    provider.user = OTHER
    assert manager.authenticate(cookie) is None
    assert not store.rows
    provider.workspace_ids = ()
    with pytest.raises(InvalidIdentity):
        manager.issue('access', 'refresh', 3600)


def test_provider_outage_preserves_encrypted_session_for_retry(setup):
    manager, store, provider, _, _, cookie, _ = setup
    provider.fail = ProviderUnavailable
    with pytest.raises(ProviderUnavailable):
        manager.authenticate(cookie)
    assert len(store.rows) == 1
    provider.fail = None
    assert manager.authenticate(cookie) is not None


def test_rejected_provider_identity_revokes_session(setup):
    manager, store, provider, _, _, cookie, _ = setup
    provider.fail = InvalidIdentity
    assert manager.authenticate(cookie) is None
    assert not store.rows


def test_refresh_serializes_across_two_managers(setup):
    manager, store, provider, now, key, cookie, _ = setup
    now[0] += 3575
    replica = SessionManager(store, provider, key, clock=lambda: now[0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda instance: instance.authenticate(cookie), [manager, replica]))
    assert all(item.user_id == USER for item in outcomes)
    assert provider.refresh_count == 1
    assert 'rotated-refresh' not in store.rows[manager.cookie_hash(cookie)].token_ciphertext


def test_refresh_rotation_survives_subsequent_provider_outage(setup):
    manager, store, provider, now, _, cookie, _ = setup
    now[0] += 3575
    provider.fail = ProviderUnavailable
    # Refresh succeeds, but the following user check becomes unavailable.
    provider.refresh = lambda refresh: ('refreshed-access', 'rotated-refresh', 3600)
    with pytest.raises(ProviderUnavailable):
        manager.authenticate(cookie)
    record = store.rows[manager.cookie_hash(cookie)]
    assert manager._tokens(record) == ('refreshed-access', 'rotated-refresh')
    assert record.last_seen_at == 1000
    provider.fail = None
    assert manager.authenticate(cookie) is not None


def test_logout_revokes_before_provider_failure_and_is_idempotent(setup):
    manager, store, provider, _, _, cookie, _ = setup
    provider.fail = ProviderUnavailable
    manager.logout(cookie)
    assert not store.rows
    assert provider.logout_count == 1
    manager.logout(cookie)
    assert manager.authenticate(cookie) is None


@pytest.fixture
def client(setup):
    manager, *_ = setup
    settings = AuthSettings(_env_file=None, app_env='production', app_origin='https://app.example.test')
    app = FastAPI()
    app.include_router(router)
    app.include_router(persistence_router)
    app.dependency_overrides[get_boundary] = lambda: (settings, manager)
    with TestClient(app, base_url='https://app.example.test') as browser:
        yield browser


def test_anonymous_private_requests_are_denied(client):
    # This fixture has no auth-flow database; bootstrap fails closed.
    assert client.get('/api/auth/session').status_code == 503
    assert client.get(f'/api/workspaces/{WORKSPACE}/session').status_code == 401
    assert client.get(f'/api/workspaces/{WORKSPACE}/summary').status_code == 401


def test_workspace_summary_is_membership_scoped_and_no_store(client, setup):
    _, _, _, _, _, cookie, _ = setup
    client.cookies.set('__Host-opsbrain_session', cookie)
    response = client.get(f'/api/workspaces/{WORKSPACE}/summary')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['profile']['display_name'] == 'Client A'
    assert client.get(f'/api/workspaces/{OTHER}/summary').status_code == 404
    assert 'secret-access' not in response.text


def test_summary_provider_reads_profile_projects_with_user_jwt_and_validates_scope():
    calls = []
    def respond(request):
        calls.append(request)
        if request.url.path == '/rest/v1/workspaces':
            return httpx.Response(200, json=[{'id': WORKSPACE, 'name': 'My workspace'}])
        if request.url.path == '/rest/v1/profiles':
            return httpx.Response(200, json=[{'user_id': USER, 'display_name': 'Client A'}])
        return httpx.Response(200, json=[{'id': OTHER, 'workspace_id': WORKSPACE, 'title': 'Incident review',
                                        'updated_at': '2026-10-12T12:00:00+00:00', 'version': 1}])
    provider = SupabaseProvider('https://provider.example.test', 'sb_publishable_synthetic', transport=httpx.MockTransport(respond))
    data = provider.workspace_summary('scoped-user-token', USER, WORKSPACE)
    assert data['recent_projects'][0]['title'] == 'Incident review'
    assert all(request.headers['authorization'] == 'Bearer scoped-user-token' for request in calls)
    assert calls[0].url.params['id'] == f'eq.{WORKSPACE}'
    assert calls[1].url.params['user_id'] == f'eq.{USER}'
    assert calls[2].url.params['workspace_id'] == f'eq.{WORKSPACE}'
    assert calls[2].url.params['limit'] == '10'


@pytest.mark.parametrize('bad_scope', ['profile', 'project'])
def test_summary_rejects_mismatched_provider_rows(bad_scope):
    def respond(request):
        if request.url.path == '/rest/v1/workspaces':
            body = [{'id': WORKSPACE, 'name': 'My workspace'}]
        elif request.url.path == '/rest/v1/profiles':
            body = [{'user_id': OTHER if bad_scope == 'profile' else USER, 'display_name': 'Client'}]
        else:
            body = [{'id': OTHER, 'workspace_id': OTHER if bad_scope == 'project' else WORKSPACE,
                     'title': 'Project', 'updated_at': '2026-10-12T12:00:00Z', 'version': 1}]
        return httpx.Response(200, json=body)
    provider = SupabaseProvider('https://provider.example.test', 'key', transport=httpx.MockTransport(respond))
    with pytest.raises(ProviderUnavailable):
        provider.workspace_summary('token', USER, WORKSPACE)


def test_session_response_contains_only_safe_state_and_authorized_workspace(client, setup):
    manager, _, _, _, _, cookie, _ = setup
    client.cookies.set('__Host-opsbrain_session', cookie)
    response = client.get('/api/auth/session')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['workspace_ids'] == [WORKSPACE]
    assert response.json()['csrf_token'] == manager.csrf_token(cookie)
    assert 'secret-access' not in response.text and 'secret-refresh' not in response.text
    assert client.get(f'/api/workspaces/{WORKSPACE}/session').status_code == 200
    assert client.get(f'/api/workspaces/{OTHER}/session').status_code == 404


def test_logout_requires_exact_origin_csrf_and_clears_secure_cookie(client, setup):
    manager, _, _, _, _, cookie, _ = setup
    client.cookies.set('__Host-opsbrain_session', cookie)
    valid = {'Origin': 'https://app.example.test', 'X-CSRF-Token': manager.csrf_token(cookie)}
    for headers in [{}, {**valid, 'Origin': 'https://evil.example.test'}, {**valid, 'X-CSRF-Token': 'forged'}]:
        assert client.post('/api/auth/logout', headers=headers).status_code == 403
        assert manager.authenticate(cookie) is not None
    response = client.post('/api/auth/logout', headers=valid)
    assert response.status_code == 200
    header = response.headers['set-cookie']
    assert 'Secure' in header and 'HttpOnly' in header and 'SameSite=lax' in header and 'Path=/' in header
    assert 'Domain=' not in header
    assert manager.authenticate(cookie) is None


def test_cookie_issuance_preserves_host_prefix_security(setup):
    _, _, _, _, _, cookie, _ = setup
    settings = AuthSettings(_env_file=None, app_env='production')
    response = JSONResponse({'ok': True})
    set_session_cookie(response, settings, cookie)
    header = response.headers['set-cookie']
    for value in ('__Host-opsbrain_session=', 'Secure', 'HttpOnly', 'Path=/', 'SameSite=lax', 'Max-Age=604800'):
        assert value in header
    assert 'Domain=' not in header


def test_unconfigured_backend_returns_safe_503(monkeypatch):
    def unavailable():
        raise ValueError('SECRET connection credentials')
    monkeypatch.setattr('orchestrator.auth.routes.configured_boundary', unavailable)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as browser:
        response = browser.get('/api/auth/session')
        assert response.status_code == 503
        assert 'SECRET' not in response.text


def test_provider_calls_validate_identity_and_scope_rls_requests():
    calls = []
    def respond(request):
        calls.append(request)
        if request.url.path == '/auth/v1/user':
            return httpx.Response(200, json={'id': USER, 'email_confirmed_at': '2026-10-12T00:00:00Z'})
        if request.url.path == '/rest/v1/workspaces':
            return httpx.Response(200, json=[{'id': WORKSPACE}])
        if request.url.path == '/auth/v1/token':
            return httpx.Response(200, json={'access_token': 'new-access', 'refresh_token': 'new-refresh', 'expires_in': 3600})
        return httpx.Response(204)
    provider = SupabaseProvider('https://provider.example.test', 'sb_publishable_synthetic', transport=httpx.MockTransport(respond))
    assert provider.verified_user('user-access') == USER
    assert provider.workspaces('user-access') == (WORKSPACE,)
    assert provider.refresh('refresh') == ('new-access', 'new-refresh', 3600)
    provider.logout('user-access')
    assert calls[1].headers['authorization'] == 'Bearer user-access'
    assert calls[1].headers['apikey'].startswith('sb_publishable_')
    assert calls[2].url.params['grant_type'] == 'refresh_token'
    assert calls[3].url.params['scope'] == 'local'


@pytest.mark.parametrize('body', [{}, {'id': USER, 'email_confirmed_at': None},
                                {'id': USER, 'email_confirmed_at': 'date', 'is_anonymous': True},
                                {'id': USER, 'email_confirmed_at': 'date', 'banned_until': '2099-01-01T00:00:00Z'}])
def test_provider_rejects_unverified_or_anonymous_users(body):
    provider = SupabaseProvider('https://provider.example.test', 'key', transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    with pytest.raises(InvalidIdentity):
        provider.verified_user('token')


def test_settings_require_tls_and_mask_private_values():
    settings = AuthSettings(_env_file=None, app_env='production', app_origin='http://evil.example.test',
                            supabase_url='https://provider.example.test', supabase_publishable_key='sb_publishable_synthetic',
                            session_encryption_key=Fernet.generate_key().decode(),
                            supabase_session_database_url='postgresql://server:private-password@database.example.test/db')
    assert 'private-password' not in repr(settings)
    with pytest.raises(ValueError):
        settings.validate_setup()
    settings.app_origin = 'https://app.example.test'
    with pytest.raises(ValueError):
        settings.validate_setup()


def test_persistence_mutations_require_origin_csrf_and_server_owned_identity(client,setup):
    manager,_,provider,_,_,cookie,_=setup
    client.cookies.set('__Host-opsbrain_session',cookie)
    command={'request_id':OTHER,'operation':'profile.update','record_id':None,'expected_version':1,
             'changes':{'display_name':'User','preferences':{'default_section':'projects','reduced_motion':True}}}
    headers={'Origin':'https://app.example.test','X-CSRF-Token':manager.csrf_token(cookie)}
    url=f'/api/workspaces/{WORKSPACE}/mutations'
    assert client.post(url,json=command).status_code==403
    assert client.post(url,json=command,headers=headers).status_code==200
    assert provider.last_mutation[0]==USER
    command['record_id']=OTHER
    assert client.post(url,json=command,headers=headers).status_code==422
    assert client.post(f'/api/workspaces/{OTHER}/mutations',json={**command,'record_id':None},headers=headers).status_code==404


def test_persistence_rejects_forged_owner_hidden_context_and_live_provenance(client,setup):
    manager,_,_,_,_,cookie,_=setup
    client.cookies.set('__Host-opsbrain_session',cookie)
    command={'request_id':OTHER,'record_id':OTHER,'operation':'project.create','expected_version':0,'changes':{'title':'Project','owner_id':OTHER}}
    headers={'Origin':'https://app.example.test','X-CSRF-Token':manager.csrf_token(cookie)}
    response=client.post(f'/api/workspaces/{WORKSPACE}/mutations',json=command,headers=headers)
    assert response.status_code==422 and 'owner_id' not in response.text
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SavedPayload.model_validate({'mode':'live','turns':[]})
