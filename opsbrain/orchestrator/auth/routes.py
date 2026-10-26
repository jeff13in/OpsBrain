"""Session inspection, logout and protected workspace boundary.

Login/email/callback exchanges are deliberately not enabled by this increment.
"""

import hmac
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from orchestrator.auth.flows import AccountFlows, PostgresAuthStore, Throttled
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


def get_account_flows(boundary: Boundary):
    settings, manager = boundary
    return AccountFlows(PostgresAuthStore(settings.supabase_session_database_url.get_secret_value()), manager)


Flows = Annotated[AccountFlows, Depends(get_account_flows)]


def flow_cookie(settings):
    return '__Host-opsbrain_flow' if settings.secure_cookie else 'opsbrain_flow_dev'


def set_flow_cookie(response, settings, cookie, max_age=3600):
    response.set_cookie(flow_cookie(settings), cookie, max_age=max_age, path='/',
                        secure=settings.secure_cookie, httponly=True, samesite='lax')


@router.get('/api/auth/session')
def session(request: Request, boundary: Boundary, flows: Flows):
    settings, manager = boundary
    cookie, principal = inspect(request, boundary)
    if principal is None:
        flow = request.cookies.get(flow_cookie(settings))
        try:
            flows.limit(request.client.host if request.client else 'unknown', 'bootstrap')
            context = flows.context(flow)
            if context is None:
                flow = flows.issue()
            response = JSONResponse({'authenticated': False, 'signup_enabled': settings.beta_signup_enabled,
                                     'google_enabled': settings.google_auth_enabled,
                                     'recovery_allowed': bool(context and context['user_id']),
                                     'csrf_token': flows.csrf(flow)}, headers={'Cache-Control': 'no-store'})
            set_flow_cookie(response, settings, flow, max_age=900 if context and context['user_id'] else 3600)
        except Throttled as exc:
            raise HTTPException(429, 'Please wait before trying again', headers={'Retry-After': str(exc.retry_after)}) from None
        except (ValueError, psycopg.Error, ProviderUnavailable):
            raise HTTPException(503, 'Account access unavailable') from None
        clear_cookie(response, settings)
        return response
    return JSONResponse({
        'authenticated': True, 'verified': True, 'signup_enabled': False, 'google_enabled': False, 'recovery_allowed': False,
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
