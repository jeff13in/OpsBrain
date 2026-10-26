"""Same-origin beta host: static allowlist and account APIs only.

Run with uvicorn orchestrator.client:app --no-access-log. The legacy engineer
orchestrator remains a separate private process; no live routes are mounted here.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from orchestrator.auth.accounts import router as accounts_router
from orchestrator.auth.google import router as google_router
from orchestrator.auth.passages import router as passages_router
from orchestrator.auth.persistence import router as persistence_router
from orchestrator.auth.routes import router as auth_router
from orchestrator.auth.security import install_account_response_policy

app = FastAPI(title='OpsBrain Client', docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth_router)
app.include_router(persistence_router)
app.include_router(passages_router)
app.include_router(accounts_router)
app.include_router(google_router)
install_account_response_policy(app)

ROOT = Path(__file__).resolve().parents[1] / 'web' / 'public'
ASSETS = frozenset(('index.html', 'styles.css', 'app.js', 'ui.js', 'demo.js', 'chat.js',
                   'monitoring.js', 'history.js', 'api.js', 'auth.js', 'route-guards.js',
                   'workspace.js', 'persistence.js', 'investigation.js', 'sources.js', 'source-api.js', 'mark.svg'))
STATIC_HEADERS = {
    'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
}


@app.api_route('/', methods=['GET', 'HEAD'])
def home():
    return FileResponse(ROOT / 'index.html', headers=STATIC_HEADERS)


@app.api_route('/{asset}', methods=['GET', 'HEAD'])
def static_asset(asset: str):
    if asset not in ASSETS:
        raise HTTPException(404, 'Not found')
    return FileResponse(ROOT / asset, headers=STATIC_HEADERS)
