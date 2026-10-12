"""Account response failures must not leak/cache input or provider secrets."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from orchestrator.auth.security import HEADERS, install_account_response_policy


@pytest.fixture
def client():
    app = FastAPI()
    install_account_response_policy(app)

    @app.get('/api/workspaces/{workspace_id}/session')
    def session(workspace_id: UUID):
        raise HTTPException(403, 'Denied')

    @app.get('/api/auth/crash')
    def crash():
        raise RuntimeError('private-provider-token-do-not-expose')

    @app.get('/api/auth/session')
    def valid():
        return {'authenticated': True}

    @app.get('/legacy/{record_id}')
    def legacy(record_id: UUID):
        return {'id': str(record_id)}

    return TestClient(app)


@pytest.mark.parametrize('path,status', [
    ('/api/auth/session', 200),
    ('/api/auth/unimplemented', 404),
    ('/api/workspaces/00000000-0000-4000-8000-000000000002/session', 403),
    ('/api/workspaces/sensitive-input/session', 422),
    ('/api/auth/crash', 500),
])
def test_account_response_policy_covers_success_and_failures(client, path, status, caplog):
    response = client.get(path)
    assert response.status_code == status
    for name, value in HEADERS.items():
        assert response.headers[name] == value
    assert 'sensitive-input' not in response.text
    assert 'private-provider-token-do-not-expose' not in response.text + caplog.text


def test_policy_does_not_change_legacy_validation(client):
    response = client.get('/legacy/invalid-uuid')
    assert response.status_code == 422
    assert 'detail' in response.json()
    assert 'cache-control' not in response.headers


def test_production_app_installs_account_policy(monkeypatch):
    from orchestrator.auth.routes import get_boundary
    from orchestrator.main import app

    def unavailable():
        raise HTTPException(503, 'Account access unavailable')

    monkeypatch.setitem(app.dependency_overrides, get_boundary, unavailable)
    response = TestClient(app).get('/api/auth/session')
    assert response.status_code == 503
    assert response.headers['cache-control'] == 'no-store'


SCAN = Path(__file__).resolve().parents[1] / 'scripts/check-public-secrets.py'
spec = importlib.util.spec_from_file_location('public_scan', SCAN)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


@pytest.mark.parametrize('credential', [
    '-----BEGIN PRIVATE KEY-----',
    'sb_secret_' + 'a' * 30,
    'eyJ' + 'a' * 10 + '.' + 'b' * 10 + '.' + 'c' * 10,
    'sk-proj-' + 'a' * 30,
    'AKIA' + 'B' * 16,
    'postgresql://username:password@example.invalid/db',
    'github_pat_' + 'a' * 30,
])
def test_scan_fails_without_printing_matched_value(tmp_path, credential):
    (tmp_path / 'app.js').write_text(credential)
    result = subprocess.run([sys.executable, str(SCAN), str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 1
    assert 'app.js: credential pattern' in result.stderr
    assert credential not in result.stdout + result.stderr


def test_scan_accepts_publishable_key_and_rejects_empty_build(tmp_path):
    (tmp_path / 'app.js').write_text('sb_publishable_' + 'a' * 30)
    assert scanner.scan(tmp_path) == []
    empty = tmp_path / 'empty'
    empty.mkdir()
    result = subprocess.run([sys.executable, str(SCAN), str(empty)], capture_output=True)
    assert result.returncode == 2
