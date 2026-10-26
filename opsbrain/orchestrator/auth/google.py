"""Server-side Google sign-in through the provider's PKCE authorization-code flow.

Provider tokens never reach the browser: the callback exchanges a one-time code
with a verifier bound to an HttpOnly cookie, then issues the normal session.
"""

import re
from urllib.parse import urlencode

import psycopg
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from orchestrator.auth.flows import Throttled
from orchestrator.auth.routes import Boundary, Flows, set_session_cookie
from orchestrator.auth.sessions import (
    InvalidIdentity,
    PersistenceError,
    ProviderUnavailable,
)

router = APIRouter()
FAILURE = '/#/login?google=failed'


def oauth_cookie(settings):
    return '__Host-opsbrain_oauth' if settings.secure_cookie else 'opsbrain_oauth_dev'


def clear_oauth_cookie(response, settings):
    response.delete_cookie(oauth_cookie(settings), path='/', secure=settings.secure_cookie, httponly=True, samesite='lax')


@router.get('/auth/google/start')
def google_start(request: Request, boundary: Boundary, flows: Flows):
    settings, _ = boundary
    if not settings.google_auth_enabled:
        raise HTTPException(404, 'Not found')
    try:
        flows.limit(request.client.host if request.client else 'unknown', 'google')
        state, challenge = flows.begin_oauth()
    except (Throttled, psycopg.Error, ProviderUnavailable):
        return RedirectResponse(FAILURE, status_code=303)
    query = urlencode({'provider': 'google', 'redirect_to': settings.app_origin.rstrip('/') + '/auth/google/callback',
                       'code_challenge': challenge, 'code_challenge_method': 's256', 'scopes': 'email profile'})
    response = RedirectResponse(settings.supabase_url.rstrip('/') + '/auth/v1/authorize?' + query, status_code=303)
    response.set_cookie(oauth_cookie(settings), state, max_age=600, path='/',
                        secure=settings.secure_cookie, httponly=True, samesite='lax')
    return response


@router.get('/auth/google/callback')
def google_callback(request: Request, boundary: Boundary, flows: Flows):
    settings, manager = boundary
    if not settings.google_auth_enabled:
        raise HTTPException(404, 'Not found')
    # Exactly one code parameter; provider errors and cancellations fail generically.
    pairs = list(request.query_params.multi_items())
    response = RedirectResponse(FAILURE, status_code=303)
    try:
        if len(pairs) != 1 or pairs[0][0] != 'code' or not re.fullmatch(r'[A-Za-z0-9_-]{16,512}', pairs[0][1]):
            raise InvalidIdentity()
        flows.limit(request.client.host if request.client else 'unknown', 'google-callback')
        verifier = flows.take_oauth(request.cookies.get(oauth_cookie(settings)))
        if not verifier:
            raise InvalidIdentity()
        tokens = manager.provider.exchange_code(pairs[0][1], verifier)
        try:
            # The invite gate and personal workspace are enforced by the user-JWT RPC.
            manager.provider.provision(tokens[0])
            new_cookie, _ = manager.issue(*tokens)
        except Exception:
            try:
                manager.provider.logout(tokens[0])
            except (InvalidIdentity, ProviderUnavailable, Throttled):
                pass
            raise
        manager.logout(request.cookies.get(settings.cookie_name))
        response = RedirectResponse('/#/workspace', status_code=303)
        set_session_cookie(response, settings, new_cookie)
    except (InvalidIdentity, PersistenceError, ProviderUnavailable, Throttled, psycopg.Error, ValueError):
        pass
    clear_oauth_cookie(response, settings)
    return response
