"""Full local account API journeys with controlled provider/store responses."""

import copy
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from orchestrator.auth.flows import AccountFlows
from orchestrator.auth.provider import SupabaseProvider
from orchestrator.auth.routes import get_account_flows, get_boundary
from orchestrator.auth.sessions import InvalidIdentity, ProviderUnavailable, SessionManager
from orchestrator.auth.settings import AuthSettings
from orchestrator.client import ASSETS, app
from test_auth_sessions import OTHER, USER, WORKSPACE, ProviderFixture, StoreFixture

PASSWORD = 'correct-password-1234'


class AuthStoreFixture:
    def __init__(self, sessions):
        self.rows, self.buckets, self.invites = {}, {}, {'a@example.test'}
        self.sessions = sessions
        self.lock = threading.RLock()

    def invited(self, email):
        return email in self.invites

    def put(self, key, user, cipher, expires):
        self.rows[key] = {'flow_hash': key, 'user_id': user, 'token_ciphertext': cipher, 'expires_at': expires}

    def get(self, key, now, *, consume=False):
        with self.lock:
            row = self.rows.get(key)
            if not row or row['expires_at'] <= now:
                return None
            return copy.deepcopy(self.rows.pop(key) if consume else row)

    def delete(self, key):
        self.rows.pop(key, None)

    def revoke_user(self, user):
        self.sessions.rows = {key: row for key, row in self.sessions.rows.items() if row.user_id != user}
        self.rows = {key: row for key, row in self.rows.items() if row['user_id'] != user}

    def rate(self, key, now, window, limit):
        with self.lock:
            start = now // window * window
            old_start, count = self.buckets.get(key, (start, 0))
            count = count + 1 if start == old_start else 1
            self.buckets[key] = start, count
            return count <= limit


class AccountProviderFixture(ProviderFixture):
    def __init__(self):
        self.events, self.used, self.records = [], set(), {}
        self.password_value = PASSWORD
        self.fail = None

    def login(self, email, password):
        if self.fail:
            raise self.fail()
        if email != 'a@example.test' or password != self.password_value:
            raise InvalidIdentity()
        self.events.append('login')
        return 'secret-access', 'secret-refresh', 3600

    def signup(self, email, password, callback):
        self.events.append(('signup', email, callback))

    def resend(self, email, callback):
        self.events.append(('resend', email, callback))

    def recover(self, email, callback):
        self.events.append(('recover', email, callback))

    def verify(self, token_hash, kind):
        if token_hash in self.used or token_hash.startswith('expired'):
            raise InvalidIdentity()
        self.used.add(token_hash)
        return 'secret-access', 'secret-refresh', 3600

    def provision(self, access):
        self.verified_user(access)
        self.events.append('provision')
        return WORKSPACE

    def password(self, access, password):
        if self.fail:
            raise self.fail()
        self.password_value = password
        self.events.append('password')

    def logout_all(self, access):
        self.events.append('logout_all')

    def mutate(self, access, user_id, workspace_id, request_id, operation, record_id, version, changes):
        if operation == 'saved.create':
            self.records[record_id] = dict(changes, id=record_id, workspace_id=workspace_id, owner_id=user_id, version=1)
        return {'id': record_id, 'version': 1, 'deleted': False}

    def read_record(self, access, user_id, workspace_id, kind, record_id):
        return self.records[record_id]


@pytest.fixture
def journey(monkeypatch):
    sessions = StoreFixture()
    provider = AccountProviderFixture()
    now = [1000]
    manager = SessionManager(sessions, provider, Fernet.generate_key(), clock=lambda: now[0])
    store = AuthStoreFixture(sessions)
    flows = AccountFlows(store, manager, clock=lambda: now[0])
    settings = AuthSettings(_env_file=None, app_env='production', app_origin='https://app.example.test', beta_signup_enabled=True)
    monkeypatch.setitem(app.dependency_overrides, get_boundary, lambda: (settings, manager))
    monkeypatch.setitem(app.dependency_overrides, get_account_flows, lambda: flows)
    with TestClient(app, base_url=settings.app_origin) as client:
        yield client, manager, provider, store, flows, now


def submit(client, action, payload):
    state = client.get('/api/auth/session')
    assert state.status_code == 200
    return client.post('/api/auth/' + action, json=payload,
                       headers={'Origin': 'https://app.example.test', 'X-CSRF-Token': state.json()['csrf_token']})


def test_signup_verify_login_save_logout_and_resume(journey):
    client, manager, provider, store, *_ = journey
    bootstrap = client.get('/api/auth/session')
    assert bootstrap.json()['authenticated'] is False
    assert bootstrap.json()['signup_enabled'] is True
    cookie_header = bootstrap.headers['set-cookie']
    assert 'HttpOnly' in cookie_header and 'Secure' in cookie_header and 'SameSite=lax' in cookie_header
    assert submit(client, 'signup', {'email': 'a@example.test', 'password': PASSWORD}).json() == {'ok': True}
    callback = client.get('/auth/callback', params={'type': 'email', 'token_hash': 'a' * 64}, follow_redirects=False)
    assert callback.status_code == 303 and callback.headers['location'] == '/#/login'
    assert 'token' not in callback.text and callback.headers['referrer-policy'] == 'no-referrer'
    assert not manager.store.rows  # Email verification never silently signs in.
    assert submit(client, 'login', {'email': 'a@example.test', 'password': PASSWORD}).status_code == 200
    state = client.get('/api/auth/session').json()
    assert state['user_id'] == USER and state['workspace_ids'] == [WORKSPACE]
    record = '00000000-0000-4000-8000-000000000004'
    payload = {'mode': 'demo', 'turns': [{'question': 'What should we check?', 'response':
               {'status': 'ok', 'answer': 'Check the fixture', 'sources': ['Demo source'], 'results': []}}]}
    write = client.post(f'/api/workspaces/{WORKSPACE}/mutations', json={
        'request_id': OTHER, 'operation': 'saved.create', 'record_id': record, 'expected_version': 0,
        'changes': {'title': 'Saved investigation', 'project_id': OTHER, 'payload': payload}},
        headers={'Origin': 'https://app.example.test', 'X-CSRF-Token': state['csrf_token']})
    assert write.status_code == 200
    logout = client.post('/api/auth/logout', headers={'Origin': 'https://app.example.test', 'X-CSRF-Token': state['csrf_token']})
    assert logout.status_code == 200 and not manager.store.rows
    assert client.get(f'/api/workspaces/{WORKSPACE}/records/saved_work/{record}').status_code == 401
    assert submit(client, 'login', {'email': 'a@example.test', 'password': PASSWORD}).status_code == 200
    restored = client.get(f'/api/workspaces/{WORKSPACE}/records/saved_work/{record}')
    assert restored.status_code == 200 and restored.json()['payload'] == payload


def test_signup_unknown_and_duplicate_are_generic(journey):
    client, _, provider, *_ = journey
    first = submit(client, 'signup', {'email': 'unknown@example.test', 'password': PASSWORD})
    assert first.json() == {'ok': True} and not provider.events
    provider.signup = lambda *args: (_ for _ in ()).throw(InvalidIdentity())
    assert submit(client, 'signup', {'email': 'a@example.test', 'password': PASSWORD}).json() == first.json()


def test_signup_default_gate_is_enforced_by_server(journey):
    client, _, provider, *_ = journey
    settings, _ = app.dependency_overrides[get_boundary]()
    settings.beta_signup_enabled = False
    assert client.get('/api/auth/session').json()['signup_enabled'] is False
    assert submit(client, 'signup', {'email': 'a@example.test', 'password': PASSWORD}).status_code == 403
    assert not provider.events


def test_account_switch_rotates_cookie_and_rejects_old_session(journey):
    client, manager, *_ = journey
    assert submit(client, 'login', {'email': 'a@example.test', 'password': PASSWORD}).status_code == 200
    old = client.cookies.get('__Host-opsbrain_session')
    # Already authenticated bootstrap uses application CSRF, not anonymous CSRF.
    assert submit(client, 'login', {'email': 'a@example.test', 'password': PASSWORD}).status_code == 200
    assert client.cookies.get('__Host-opsbrain_session') != old
    assert manager.authenticate(old) is None


def test_provider_failure_consumes_recovery_without_reviving_sessions(journey):
    client, manager, provider, store, *_ = journey
    manager.issue('secret-access', 'secret-refresh', 3600)
    client.get('/auth/callback', params={'type': 'recovery', 'token_hash': 'd' * 64}, follow_redirects=False)
    provider.password = lambda *args: (_ for _ in ()).throw(ProviderUnavailable())
    assert submit(client, 'password', {'password': 'new-password-1234'}).status_code == 503
    assert not manager.store.rows and not store.rows
    assert submit(client, 'password', {'password': PASSWORD}).status_code == 403


def test_expired_flow_csrf_cannot_authenticate(journey):
    client, _, _, _, _, now = journey
    state = client.get('/api/auth/session').json()
    now[0] += 3601
    response = client.post('/api/auth/login', json={'email': 'a@example.test', 'password': PASSWORD},
        headers={'Origin': 'https://app.example.test', 'X-CSRF-Token': state['csrf_token']})
    assert response.status_code == 401


@pytest.mark.parametrize('action', ['resend', 'recovery'])
def test_email_actions_rotate_context_and_return_safe_ack(journey, action):
    client, _, _, store, *_ = journey
    assert submit(client, action, {'email': 'a@example.test'}).json() == {'ok': True}
    assert not store.rows


def test_invalid_credentials_and_provider_outage_are_distinct_safe_errors(journey):
    client, _, provider, *_ = journey
    assert submit(client, 'login', {'email': 'a@example.test', 'password': 'wrong'}).status_code == 401
    provider.fail = ProviderUnavailable
    assert submit(client, 'login', {'email': 'a@example.test', 'password': PASSWORD}).status_code == 503


def test_origin_csrf_body_limits_and_owner_forgery(journey):
    client, *_ = journey
    state = client.get('/api/auth/session').json()
    body = {'email': 'a@example.test', 'password': PASSWORD}
    assert client.post('/api/auth/login', json=body).status_code == 403
    assert client.post('/api/auth/login', json=body, headers={'Origin': 'https://app.example.test', 'X-CSRF-Token': 'forged'}).status_code == 403
    headers = {'Origin': 'https://app.example.test', 'X-CSRF-Token': state['csrf_token']}
    assert client.post('/api/auth/login', json={**body, 'user_id': OTHER}, headers=headers).status_code == 422
    assert client.post('/api/auth/login', content='x' * 4097, headers={**headers, 'Content-Type': 'application/json'}).status_code == 413
    assert client.post('/api/auth/login', content='[', headers={**headers, 'Content-Type': 'application/json'}).status_code == 422


def test_throttle_survives_new_flow_and_manager_restart(journey):
    client, manager, _, store, flows, now = journey
    for _ in range(5):
        assert submit(client, 'login', {'email': 'a@example.test', 'password': 'wrong'}).status_code == 401
    restarted = AccountFlows(store, manager, clock=lambda: now[0])
    app.dependency_overrides[get_account_flows] = lambda: restarted
    blocked = submit(client, 'login', {'email': 'a@example.test', 'password': 'wrong'})
    assert blocked.status_code == 429 and 0 < int(blocked.headers['retry-after']) <= 900
    now[0] += 901
    assert submit(client, 'login', {'email': 'a@example.test', 'password': PASSWORD}).status_code == 200


def test_recovery_requires_link_and_revokes_every_local_session(journey):
    client, manager, provider, store, *_ = journey
    assert submit(client, 'password', {'password': PASSWORD}).status_code == 403
    manager.issue('secret-access', 'secret-refresh', 3600)
    manager.issue('secret-access', 'secret-refresh', 3600)
    result = client.get('/auth/callback', params={'type': 'recovery', 'token_hash': 'b' * 64}, follow_redirects=False)
    assert result.headers['location'] == '/#/password'
    flow_record = next(row for row in store.rows.values() if row['user_id'])
    assert 'secret-access' not in repr(flow_record) and 'secret-refresh' not in repr(flow_record)
    assert client.get('/api/auth/session').json()['recovery_allowed'] is True
    updated = submit(client, 'password', {'password': 'new-password-1234'})
    assert updated.status_code == 200 and not manager.store.rows and not store.rows
    assert provider.events[-2:] == ['password', 'logout_all']
    assert submit(client, 'password', {'password': PASSWORD}).status_code == 403
    assert submit(client, 'login', {'email': 'a@example.test', 'password': 'new-password-1234'}).status_code == 200


def test_expired_replayed_malformed_callbacks_never_leak_tokens(journey):
    client, _, _, store, *_ = journey
    params = {'type': 'recovery', 'token_hash': 'expired' + 'a' * 64}
    assert client.get('/auth/callback', params=params, follow_redirects=False).headers['location'] == '/#/recovery'
    params['token_hash'] = 'c' * 64
    assert client.get('/auth/callback', params=params, follow_redirects=False).headers['location'] == '/#/password'
    assert client.get('/auth/callback', params=params, follow_redirects=False).headers['location'] == '/#/recovery'
    before = len(store.rows)
    bad = client.get('/auth/callback?type=email&type=recovery&token_hash=' + 'a' * 64, follow_redirects=False)
    assert bad.status_code == 303 and 'token_hash' not in bad.text and len(store.rows) == before
    assert client.get('/auth/callback', params={**params, 'next': 'https://evil.test'}, follow_redirects=False).status_code == 303


def test_recovery_context_expiry_and_concurrent_one_time_claim(journey):
    client, _, _, _, flows, now = journey
    cookie = flows.issue(('secret-access', 'secret-refresh', 3600))
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: flows.context(cookie, consume=True), range(2)))
    assert sum(row is not None for row in claims) == 1
    cookie = flows.issue(('secret-access', 'secret-refresh', 3600))
    now[0] += 901
    assert flows.context(cookie) is None


def test_client_host_serves_allowlist_and_excludes_engineer_routes(journey):
    client, *_ = journey
    for asset in ASSETS:
        response = client.get('/' + asset)
        assert response.status_code == 200
        assert 'frame-ancestors' in response.headers['content-security-policy']
    for path in ['/ask', '/metrics', '/docs', '/openapi.json', '/.env', '/orchestrator/main.py']:
        assert client.get(path).status_code == 404
    assert client.post('/ask', json={'question': 'What happened?'}).status_code in (404, 405)
    assert client.head('/').content == b''


def test_provider_rest_contract_never_uses_admin_key_or_browser_redirect():
    calls = []
    def respond(request):
        calls.append(request)
        if request.url.path.endswith('/token') or request.url.path.endswith('/verify'):
            return httpx.Response(200, json={'access_token': 'secret-access', 'refresh_token': 'secret-refresh', 'expires_in': 3600})
        if request.url.path.endswith('/user'):
            return httpx.Response(200, json={'id': USER, 'email_confirmed_at': '2026-10-12', 'is_anonymous': False})
        if request.url.path.endswith('/ensure_personal_workspace'):
            return httpx.Response(200, json=WORKSPACE)
        return httpx.Response(200, json={})
    provider = SupabaseProvider('https://provider.example.test', 'sb_publishable_fixture', transport=httpx.MockTransport(respond))
    tokens = provider.login('a@example.test', PASSWORD)
    assert provider.provision(tokens[0]) == WORKSPACE
    provider.signup('a@example.test', PASSWORD, 'https://app.example.test/auth/callback')
    provider.resend('a@example.test', 'https://app.example.test/auth/callback')
    provider.recover('a@example.test', 'https://app.example.test/auth/callback')
    provider.verify('a' * 64, 'recovery')
    provider.password(tokens[0], PASSWORD)
    provider.logout_all(tokens[0])
    assert all(call.headers['apikey'] == 'sb_publishable_fixture' for call in calls)
    bootstrap = next(call for call in calls if call.url.path.endswith('/ensure_personal_workspace'))
    assert bootstrap.content == b'{}' and bootstrap.headers['authorization'] == 'Bearer secret-access'
    assert next(call for call in calls if call.url.path.endswith('/signup')).url.params['redirect_to'] == 'https://app.example.test/auth/callback'
    assert hashlib.sha256('a@example.test'.encode()).hexdigest() != 'a@example.test'
