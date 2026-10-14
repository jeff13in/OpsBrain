"""OPU-109 local fixtures; no hosted isolation claim."""
from dataclasses import replace
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_auth_sessions import OTHER, USER, WORKSPACE, ProviderFixture, StoreFixture

from orchestrator.auth import passages
from orchestrator.auth.passages import PassageResolver, RetrievedPassage
from orchestrator.auth.routes import get_boundary
from orchestrator.auth.security import HEADERS, install_account_response_policy
from orchestrator.auth.sessions import SessionManager
from orchestrator.auth.settings import AuthSettings

INVESTIGATION = '00000000-0000-4000-8000-000000000004'
SOURCE = 'src_' + 'a' * 64


def record():
    return RetrievedPassage(USER, WORKSPACE, INVESTIGATION, SOURCE,
                            '<script>alert(1)</script>\nUnicode: 診断 🧠', 2000, True,
                            revision='sha256:revision', observed_at='2026-10-13T12:00:00Z')


def resolve(repo):
    return PassageResolver(repo, clock=lambda: 1000).resolve(USER, WORKSPACE, INVESTIGATION, SOURCE)


def test_bounded_exact_retrieved_content_and_metadata():
    repo = Mock(); repo.lookup.return_value = record()
    result = resolve(repo)
    assert result.available and result.passage == record().passage
    assert result.revision == record().revision and result.observed_at == record().observed_at
    repo.lookup.assert_called_once_with(USER, WORKSPACE, INVESTIGATION, SOURCE)


@pytest.mark.parametrize('identifier', ['../secret', 'https://example.test', '%2e%2e', '/etc/passwd', 'src_'+ 'a'*65, 'src_'+'A'*64, 'C:\\secret', 'src_'+'a'*64+'\n'])
def test_hostile_ids_never_reach_repository(identifier):
    repo = Mock()
    with pytest.raises(ValueError):
        PassageResolver(repo).resolve(USER, WORKSPACE, INVESTIGATION, identifier)
    repo.lookup.assert_not_called()


@pytest.mark.parametrize('change', [
    {'user_id': OTHER}, {'workspace_id': OTHER}, {'investigation_id': OTHER},
    {'source_id': 'src_'+'b'*64}, {'approved': False}, {'expires_at': 1000},
])
def test_foreign_revoked_or_expired_records_are_indistinguishable_from_missing(change):
    repo = Mock(); repo.lookup.return_value = replace(record(), **change)
    result = resolve(repo)
    assert not result.available and result.passage is None and result.revision is None
    repo.lookup.return_value = None
    assert resolve(repo) == result


def test_revocation_is_read_on_every_request_and_unknown_metadata_is_not_invented():
    repo = Mock(); repo.lookup.return_value = replace(record(), revision=None, observed_at=None)
    assert resolve(repo).revision is None
    repo.lookup.return_value = replace(record(), approved=False)
    assert not resolve(repo).available


@pytest.mark.parametrize('change', [
    {'passage': 'x'*8001}, {'passage': '  '}, {'revision': 'x'*201},
    {'observed_at': '2026-99-99T00:00:00Z'}, {'observed_at': 'private value'},
])
def test_malformed_repository_data_is_rejected(change):
    repo = Mock(); repo.lookup.return_value = replace(record(), **change)
    with pytest.raises(ValueError):
        resolve(repo)


@pytest.fixture
def boundary_client():
    store, provider = StoreFixture(), ProviderFixture()
    manager = SessionManager(store, provider, Fernet.generate_key(), clock=lambda: 1000)
    cookie, _ = manager.issue('private-access', 'private-refresh', 3600)
    settings = AuthSettings(app_env='development')
    app = FastAPI(); app.include_router(passages.router); install_account_response_policy(app)
    app.dependency_overrides[get_boundary] = lambda: (settings, manager)
    client = TestClient(app)
    return client, manager, provider, cookie


def path(workspace=WORKSPACE):
    return f'/api/workspaces/{workspace}/investigations/{INVESTIGATION}/sources/{SOURCE}'


def test_route_authentication_gate_scope_and_private_headers(boundary_client, monkeypatch):
    client, manager, provider, cookie = boundary_client
    repo = Mock(); repo.lookup.return_value = record()
    resolver = PassageResolver(repo, clock=lambda: 1000)
    monkeypatch.setattr(passages, 'get_passage_resolver', lambda: resolver)
    assert client.get(path()).status_code == 401
    repo.lookup.assert_not_called()
    client.cookies.set('opsbrain_session_dev', cookie)
    assert client.get(path(OTHER)).status_code == 404
    repo.lookup.assert_not_called()
    response = client.get(path())
    assert response.status_code == 200 and response.json()['passage'] == record().passage
    for key, value in HEADERS.items():
        assert response.headers[key] == value
    provider.workspace_ids = ()
    assert client.get(path()).status_code == 401
    provider.workspace_ids = (WORKSPACE,)
    manager.logout(cookie)
    assert client.get(path()).status_code == 401


def test_default_adapter_fails_closed_and_query_inputs_rejected(boundary_client):
    client, _, _, cookie = boundary_client
    client.cookies.set('opsbrain_session_dev', cookie)
    assert client.get(path()).status_code == 503
    response = client.get(path()+'?url=https://hostile.test')
    assert response.status_code == 422 and 'hostile' not in response.text


def test_repository_failure_is_redacted(boundary_client, monkeypatch):
    client, _, _, cookie = boundary_client
    client.cookies.set('opsbrain_session_dev', cookie)
    repo = Mock(); repo.lookup.side_effect = RuntimeError('private-db-secret')
    monkeypatch.setattr(passages, 'get_passage_resolver', lambda: PassageResolver(repo))
    response = client.get(path())
    assert response.status_code == 500 and 'private-db-secret' not in response.text
