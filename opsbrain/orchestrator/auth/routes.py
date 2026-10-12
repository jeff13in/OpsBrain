"""Session inspection, logout and protected workspace boundary.

Login/email/callback exchanges are deliberately not enabled by this increment.
"""

import hmac
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from orchestrator.auth.sessions import (
    InvalidIdentity,
    ProviderUnavailable,
    SessionManager,
    WorkspaceUnavailable,
)
from orchestrator.auth.settings import AuthSettings, configured_boundary

router = APIRouter()


def get_boundary():
    try:
        return configured_boundary()
    except (ValueError, psycopg.Error, ProviderUnavailable):
        raise HTTPException(503, 'Account access unavailable') from None


def clear_cookie(response, settings):
    response.delete_cookie(settings.cookie_name, path='/', secure=settings.secure_cookie, httponly=True, samesite='lax')


def set_session_cookie(response, settings, cookie, max_age=604800):
    """Provider exchange/callback handoff; cookie ID must be server generated."""
    if SessionManager.cookie_hash(cookie) is None:
        raise ValueError('Invalid application cookie')
    response.set_cookie(settings.cookie_name, cookie, max_age=max_age, path='/',
                        secure=settings.secure_cookie, httponly=True, samesite='lax')


def inspect(request, boundary):
    settings, manager = boundary
    cookie = request.cookies.get(settings.cookie_name)
    try:
        principal = manager.authenticate(cookie)
    except (ValueError, psycopg.Error, ProviderUnavailable):
        raise HTTPException(503, 'Account access unavailable') from None
    return cookie, principal


Boundary = Annotated[tuple[AuthSettings, SessionManager], Depends(get_boundary)]


@router.get('/api/auth/session')
def session(request: Request, boundary: Boundary):
    settings, manager = boundary
    cookie, principal = inspect(request, boundary)
    if principal is None:
        response = JSONResponse({'error': 'Authentication required'}, status_code=401, headers={'Cache-Control': 'no-store'})
        clear_cookie(response, settings)
        return response
    return JSONResponse({
        'authenticated': True, 'verified': True, 'signup_enabled': False, 'recovery_allowed': False,
        'csrf_token': manager.csrf_token(cookie), 'user_id': principal.user_id,
        'workspace_ids': list(principal.workspace_ids),
    }, headers={'Cache-Control': 'no-store'})


@router.post('/api/auth/logout')
def logout(request: Request, boundary: Boundary):
    settings, manager = boundary
    cookie = request.cookies.get(settings.cookie_name)
    if request.headers.get('origin') != settings.app_origin.rstrip('/'):
        raise HTTPException(403, 'Invalid request origin')
    try:
        expected = manager.csrf_token(cookie)
    except InvalidIdentity:
        raise HTTPException(401, 'Authentication required') from None
    supplied = request.headers.get('x-csrf-token', '')
    if not supplied.isascii() or not hmac.compare_digest(supplied, expected):
        raise HTTPException(403, 'Invalid request token')
    try:
        manager.logout(cookie)
    except (ValueError, psycopg.Error, ProviderUnavailable):
        raise HTTPException(503, 'Account access unavailable') from None
    response = JSONResponse({'ok': True}, headers={'Cache-Control': 'no-store'})
    clear_cookie(response, settings)
    return response


@router.get('/api/workspaces/{workspace_id}/session')
def workspace_session(workspace_id: UUID, request: Request, boundary: Boundary):
    _, principal = inspect(request, boundary)
    if principal is None:
        raise HTTPException(401, 'Authentication required')
    if str(workspace_id) not in principal.workspace_ids:
        raise HTTPException(404, 'Workspace unavailable')
    return JSONResponse({'workspace_id': str(workspace_id), 'user_id': principal.user_id}, headers={'Cache-Control': 'no-store'})


@router.get('/api/workspaces/{workspace_id}/summary')
def workspace_summary(workspace_id: UUID, request: Request, boundary: Boundary):
    settings, manager = boundary
    try:
        data = manager.workspace_summary(request.cookies.get(settings.cookie_name), str(workspace_id))
    except InvalidIdentity:
        raise HTTPException(401, 'Authentication required', headers={'Cache-Control': 'no-store'}) from None
    except WorkspaceUnavailable:
        raise HTTPException(404, 'Workspace unavailable', headers={'Cache-Control': 'no-store'}) from None
    except (ValueError, psycopg.Error, ProviderUnavailable):
        raise HTTPException(503, 'Workspace unavailable', headers={'Cache-Control': 'no-store'}) from None
    return JSONResponse(data, headers={'Cache-Control': 'no-store'})
