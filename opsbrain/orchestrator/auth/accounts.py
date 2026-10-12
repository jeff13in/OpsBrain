"""Bounded account exchanges; provider secrets never enter browser responses."""

import hmac
import json
import re
from types import SimpleNamespace

import psycopg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from orchestrator.auth.flows import Throttled
from orchestrator.auth.routes import (
    Boundary,
    Flows,
    clear_cookie,
    flow_cookie,
    set_flow_cookie,
    set_session_cookie,
)
from orchestrator.auth.sessions import (
    InvalidIdentity,
    PersistenceError,
    ProviderUnavailable,
)

router = APIRouter()


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    email: str = Field(min_length=3, max_length=254)
    password: str | None = Field(default=None, min_length=1, max_length=128)


def authorize(request, boundary, flows):
    settings, manager = boundary
    if request.headers.get('origin') != settings.app_origin.rstrip('/'):
        raise HTTPException(403, 'Invalid request origin')
    cookie = request.cookies.get(flow_cookie(settings))
    context = flows.context(cookie)
    supplied = request.headers.get('x-csrf-token', '')
    if context is None:
        session_cookie = request.cookies.get(settings.cookie_name)
        if (manager.cookie_hash(session_cookie) is not None and supplied.isascii()
            and hmac.compare_digest(supplied, manager.csrf_token(session_cookie))
            and manager.authenticate(session_cookie) is not None):
            return None, {'flow_hash': None, 'user_id': None}
        raise HTTPException(401, 'Session expired')
    if not supplied.isascii() or not hmac.compare_digest(supplied, flows.csrf(cookie)):
        raise HTTPException(403, 'Invalid request token')
    return cookie, context


def exchange(request, action, payload, boundary, flows):
    settings, manager = boundary
    cookie, context = authorize(request, boundary, flows)
    if action == 'signup' and not settings.beta_signup_enabled:
        raise HTTPException(403, 'Signup unavailable')
    email = payload.get('email', '')
    password = payload.get('password')
    if action == 'password':
        if set(payload) != {'password'} or not isinstance(password, str) or not 12 <= len(password) <= 128:
            raise HTTPException(422, 'Invalid account request')
    else:
        try:
            parsed = Credentials.model_validate(payload)
        except ValidationError:
            raise HTTPException(422, 'Invalid account request') from None
        email = parsed.email.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise HTTPException(422, 'Invalid account request')
        if action in ('login', 'signup'):
            if password is None or (action == 'signup' and len(password) < 12):
                raise HTTPException(422, 'Invalid account request')
        elif password is not None:
            raise HTTPException(422, 'Invalid account request')
    flows.limit(request.client.host if request.client else 'unknown', action, email or context.get('user_id'))
    response = JSONResponse({'ok': True}, headers={'Cache-Control': 'no-store'})
    provider = manager.provider
    if action == 'login':
        tokens = provider.login(email, password)
        try:
            provider.provision(tokens[0])
            new_cookie, _ = manager.issue(*tokens)
        except Exception:
            try:
                provider.logout(tokens[0])
            except (InvalidIdentity, ProviderUnavailable, Throttled):
                pass
            raise
        # Rotate all browser state only after a successful durable session issue.
        old_cookie = request.cookies.get(settings.cookie_name)
        manager.logout(old_cookie)
        set_session_cookie(response, settings, new_cookie)
    elif action == 'password':
        if not context['user_id']:
            raise HTTPException(403, 'Recovery required')
        claimed = flows.context(cookie, consume=True)
        if not claimed or not claimed['user_id']:
            raise HTTPException(401, 'Recovery expired')
        tokens = manager._tokens(SimpleNamespace(session_hash=claimed['flow_hash'], token_ciphertext=claimed['token_ciphertext']))
        if provider.verified_user(tokens[0]) != claimed['user_id']:
            raise InvalidIdentity()
        # Local revocation commits before password update/provider-global logout.
        # An outage consumes the context: request another email rather than replay.
        flows.store.revoke_user(claimed['user_id'])
        provider.password(tokens[0], password)
        provider.logout_all(tokens[0])
        clear_cookie(response, settings)
    elif action in ('signup', 'resend'):
        if flows.store.invited(email):
            try:
                if action == 'signup':
                    provider.signup(email, password, settings.app_origin.rstrip('/') + '/auth/callback')
                else:
                    provider.resend(email, settings.app_origin.rstrip('/') + '/auth/callback')
            except InvalidIdentity:
                # Duplicate/unavailable addresses receive the same acknowledgement.
                pass
    elif action == 'recovery':
        try:
            provider.recover(email, settings.app_origin.rstrip('/') + '/auth/callback')
        except InvalidIdentity:
            pass
    if context['flow_hash']:
        flows.store.delete(context['flow_hash'])
    response.delete_cookie(flow_cookie(settings), path='/', secure=settings.secure_cookie, httponly=True, samesite='lax')
    return response


@router.post('/api/auth/{action}')
async def account_exchange(action: str, request: Request, boundary: Boundary, flows: Flows):
    if action not in ('login', 'signup', 'resend', 'recovery', 'password'):
        raise HTTPException(404, 'Account action unavailable')
    if request.headers.get('origin') != boundary[0].app_origin.rstrip('/'):
        raise HTTPException(403, 'Invalid request origin')
    if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
        raise HTTPException(415, 'JSON required')
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            raise HTTPException(413, 'Request too large')
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise TypeError()
    except (ValueError, TypeError):
        raise HTTPException(422, 'Invalid account request') from None
    try:
        return await run_in_threadpool(exchange, request, action, payload, boundary, flows)
    except Throttled as exc:
        raise HTTPException(429, 'Please wait before trying again', headers={'Retry-After': str(exc.retry_after)}) from None
    except InvalidIdentity:
        raise HTTPException(401, 'Account could not be verified') from None
    except PersistenceError as exc:
        status = 401 if exc.status in (401, 403, 404) else 503
        raise HTTPException(status, 'Account could not be verified' if status == 401 else 'Account access unavailable') from None
    except (ValueError, psycopg.Error, ProviderUnavailable):
        raise HTTPException(503, 'Account access unavailable') from None


@router.get('/auth/callback')
def callback(request: Request, boundary: Boundary, flows: Flows):
    settings, manager = boundary
    # Only fixed server callback types. No next/redirect_to or browser ownership.
    pairs = list(request.query_params.multi_items())
    params = dict(pairs)
    destination = '/#/verification'
    response = None
    try:
        if len(pairs) != 2 or set(params) != {'token_hash', 'type'} or params['type'] not in ('email', 'recovery'):
            raise InvalidIdentity()
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', params['token_hash']):
            raise InvalidIdentity()
        flows.limit(request.client.host if request.client else 'unknown', 'callback')
        tokens = manager.provider.verify(params['token_hash'], params['type'])
        if params['type'] == 'recovery':
            flow = flows.issue(tokens)
            manager.logout(request.cookies.get(settings.cookie_name))
            old_flow = request.cookies.get(flow_cookie(settings))
            if manager.cookie_hash(old_flow):
                flows.store.delete(manager.cookie_hash(old_flow))
            response = RedirectResponse('/#/password', status_code=303)
            clear_cookie(response, settings)
            set_flow_cookie(response, settings, flow, max_age=900)
        else:
            try:
                manager.provider.provision(tokens[0])
            finally:
                manager.provider.logout(tokens[0])
            destination = '/#/login'
    except (InvalidIdentity, PersistenceError, ProviderUnavailable, Throttled, psycopg.Error, ValueError):
        destination = '/#/recovery' if params.get('type') == 'recovery' else '/#/verification'
    return response or RedirectResponse(destination, status_code=303)
