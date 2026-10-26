"""Server-side Google PKCE sign-in with controlled provider/store responses."""

import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from orchestrator.auth.flows import AccountFlows
from orchestrator.auth.provider import SupabaseProvider
from orchestrator.auth.routes import get_account_flows, get_boundary
from orchestrator.auth.sessions import InvalidIdentity, SessionManager
from orchestrator.auth.settings import AuthSettings
from orchestrator.client import app
from test_account_flows import AccountProviderFixture, AuthStoreFixture
from test_auth_sessions import USER, StoreFixture

ORIGIN = 'https://app.example.test'
SUPABASE = 'https://project.supabase.test'
CODE = '11111111-2222-4333-8444-555555555555'


class OAuthStoreFixture(AuthStoreFixture):
    def __init__(self, sessions):
        super().__init__(sessions)
        self.oauth = {}

    def put_oauth(self, key, verifier, expires):
        self.oauth[key] = verifier, expires

    def take_oauth(self, key, now):
        row = self.oauth.pop(key, None)
        return row[0] if row and row[1] > now else None


class GoogleProviderFixture(AccountProviderFixture):
    def __init__(self):
        super().__init__()
        self.exchanges, self.uninvited = [], False

    def exchange_code(self, auth_code, code_verifier):
        self.exchanges.append((auth_code, code_verifier))
        return 'google-access', 'google-refresh', 3600

    def provision(self, access):
        if self.uninvited:
            raise InvalidIdentity()
        return super().provision(access)


@pytest.fixture
def google(monkeypatch):
    sessions = StoreFixture()
    provider = GoogleProviderFixture()
    now = [1000]
    manager = SessionManager(sessions, provider, Fernet.generate_key(), clock=lambda: now[0])
    store = OAuthStoreFixture(sessions)
    flows = AccountFlows(store, manager, clock=lambda: now[0])
    settings = AuthSettings(_env_file=None, app_env='production', app_origin=ORIGIN,
                            supabase_url=SUPABASE, google_auth_enabled=True)
    monkeypatch.setitem(app.dependency_overrides, get_boundary, lambda: (settings, manager))
    monkeypatch.setitem(app.dependency_overrides, get_account_flows, lambda: flows)
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, settings, manager, provider, store, now


def start(client):
    response = client.get('/auth/google/start', follow_redirects=False)
    assert response.status_code == 303
    return response


def test_start_redirects_to_provider_with_s256_challenge_bound_to_cookie(google):
    client, _, _, _, store, _ = google
    response = start(client)
    target = urlsplit(response.headers['location'])
    query = parse_qs(target.query)
    assert f'{target.scheme}://{target.netloc}{target.path}' == SUPABASE + '/auth/v1/authorize'
    assert query['provider'] == ['google'] and query['code_challenge_method'] == ['s256']
    assert query['redirect_to'] == [ORIGIN + '/auth/google/callback']
    cookie = response.headers['set-cookie']
    assert cookie.startswith('__Host-opsbrain_oauth=') and 'HttpOnly' in cookie and 'Secure' in cookie
    assert 'SameSite=lax' in cookie and 'Max-Age=600' in cookie
    (verifier, _), = store.oauth.values()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    assert query['code_challenge'] == [expected] and verifier not in response.headers['location']
    assert response.headers['referrer-policy'] == 'no-referrer' and response.headers['cache-control'] == 'no-store'


def test_callback_exchanges_verifier_issues_session_and_cannot_replay(google):
    client, settings, manager, provider, store, _ = google
    start(client)
    (verifier, _), = store.oauth.values()
    response = client.get('/auth/google/callback', params={'code': CODE}, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/#/workspace'
    assert provider.exchanges == [(CODE, verifier)] and 'provision' in provider.events
    assert manager.authenticate(client.cookies.get(settings.cookie_name)).user_id == USER
    assert 'google-access' not in response.text and not store.oauth
    replay = client.get('/auth/google/callback', params={'code': CODE}, follow_redirects=False)
    assert replay.headers['location'] == '/#/login?google=failed' and len(provider.exchanges) == 1


@pytest.mark.parametrize('params', [
    {'error': 'access_denied', 'error_description': 'cancelled'},
    {'code': CODE, 'next': 'https://evil.test'},
    {'code': 'bad code!'},
    {},
])
def test_callback_rejects_errors_extra_and_malformed_parameters(google, params):
    client, settings, _, provider, _, _ = google
    start(client)
    response = client.get('/auth/google/callback', params=params, follow_redirects=False)
    assert response.headers['location'] == '/#/login?google=failed' and not provider.exchanges
    assert client.cookies.get(settings.cookie_name) is None


def test_callback_without_browser_state_or_after_expiry_is_rejected(google):
    client, settings, _, provider, _, now = google
    assert client.get('/auth/google/callback', params={'code': CODE}, follow_redirects=False).headers['location'] == '/#/login?google=failed'
    start(client)
    now[0] += 601
    response = client.get('/auth/google/callback', params={'code': CODE}, follow_redirects=False)
    assert response.headers['location'] == '/#/login?google=failed' and not provider.exchanges
    assert client.cookies.get(settings.cookie_name) is None


def test_uninvited_google_identity_is_logged_out_without_session(google):
    client, settings, _, provider, _, _ = google
    provider.uninvited = True
    start(client)
    response = client.get('/auth/google/callback', params={'code': CODE}, follow_redirects=False)
    assert response.headers['location'] == '/#/login?google=failed' and provider.logout_count == 1
    assert client.cookies.get(settings.cookie_name) is None


def test_start_is_throttled_per_peer(google):
    client, *_ = google
    for _ in range(20):
        start(client)
    assert start(client).headers['location'] == '/#/login?google=failed'


def test_google_routes_are_unavailable_unless_enabled(google, monkeypatch):
    client, settings, manager, *_ = google
    disabled = settings.model_copy(update={'google_auth_enabled': False})
    monkeypatch.setitem(app.dependency_overrides, get_boundary, lambda: (disabled, manager))
    assert client.get('/auth/google/start', follow_redirects=False).status_code == 404
    assert client.get('/auth/google/callback', params={'code': CODE}, follow_redirects=False).status_code == 404


def test_provider_pkce_exchange_payload():
    import httpx
    seen = {}

    def handler(request):
        seen['url'], seen['body'] = str(request.url), request.content
        return httpx.Response(200, json={'access_token': 'a', 'refresh_token': 'r', 'expires_in': 3600})

    provider = SupabaseProvider(SUPABASE, 'sb_publishable_x', transport=httpx.MockTransport(handler))
    assert provider.exchange_code(CODE, 'v' * 43) == ('a', 'r', 3600)
    assert seen['url'] == SUPABASE + '/auth/v1/token?grant_type=pkce'
    assert b'"auth_code"' in seen['body'] and b'"code_verifier"' in seen['body']


def test_session_bootstrap_reports_google_availability(google, monkeypatch):
    client, settings, manager, *_ = google
    assert client.get('/api/auth/session').json()['google_enabled'] is True
    disabled = settings.model_copy(update={'google_auth_enabled': False})
    monkeypatch.setitem(app.dependency_overrides, get_boundary, lambda: (disabled, manager))
    assert client.get('/api/auth/session').json()['google_enabled'] is False
