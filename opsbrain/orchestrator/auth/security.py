"""Response policy for account APIs, including failures before route execution."""

import logging

from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders

HEADERS = {
    'Cache-Control': 'no-store',
    'Pragma': 'no-cache',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
}
logger = logging.getLogger(__name__)


def private_path(path):
    return path in ('/api/auth', '/api/workspaces', '/auth/callback') or path.startswith(('/api/auth/', '/api/workspaces/'))


class AccountResponsePolicy:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not private_path(scope['path']):
            return await self.app(scope, receive, send)
        started = False

        async def protected_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
                headers = MutableHeaders(scope=message)
                for name, value in HEADERS.items():
                    headers[name] = value
            await send(message)

        try:
            await self.app(scope, receive, protected_send)
        except Exception:
            # Do not expose provider bodies, input, tokens or configuration in
            # exception responses/logs. A started response cannot be replaced.
            if started:
                raise
            logger.error('Account API request failed')
            response = JSONResponse({'error': 'Account access unavailable'}, status_code=500, headers=HEADERS)
            await response(scope, receive, send)


def install_account_response_policy(app):
    app.add_middleware(AccountResponsePolicy)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if private_path(request.url.path):
            return JSONResponse({'error': 'Invalid account request'}, status_code=422, headers=HEADERS)
        return await request_validation_exception_handler(request, error)
