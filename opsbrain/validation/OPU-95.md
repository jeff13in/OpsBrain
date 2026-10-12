# OPU-95 session and protected-routing foundation

Current closure: local implementation is complete under the user-directed
handoff. Hosted setup and release acceptance are tracked separately in OPU-99.
See [final cross-ticket evidence](week5-closure.md). The report below records
earlier increments and does not define the current completion scope.

October 12, 2026. Implemented locally; keep In Progress. OPU-93/94 dependencies
remain intact. The free-only budget is preserved.

## Delivered

- Private PostgreSQL app_sessions migration, RLS and a dedicated NOLOGIN server
  capability. Client and general service-role access is revoked; session capability
  cannot read application records or provision memberships.
- Random opaque cookies with hashed lookup, Fernet-encrypted provider token pairs
  bound to their session, seven-day absolute and 24-hour idle expiry, secure cookie
  issuance/deletion helpers and no production in-memory fallback.
- Row-locked refresh, provider identity revalidation and user-scoped/RLS workspace
  resolution. Preserve rotated tokens on a following provider outage; revoke
  rejected, tampered, expired or no-longer-authorized sessions.
- Session inspection, CSRF/exact-Origin logout and protected workspace session
  endpoints on the Orchestrator. Local session revocation commits before provider
  logout; provider failure does not resurrect application access.
- Frontend guarded Workspace entry, verified post-login routing with an internal
  destination allowlist, cancellation/stale-response suppression and logout state
  cleanup. Existing engineer API/demo history remain separate.

Affected runtime: orchestrator/auth/ (settings, provider, sessions, routes),
orchestrator/main.py, Dockerfile and requirements-dev.txt; web/public/auth.js,
route-guards.js, app.js, ui.js; asset allowlist/syntax checks. One additive private
session migration. No hosted database changed. Added cryptography>=43,<47 to
backend runtime/test requirements; Orchestrator image also installs existing
psycopg/pydantic-settings dependencies needed by the new boundary.

## Verification

| Check | Result |
| --- | --- |
| Focused Python session/provider/router suite | 24 passed on Python 3.12.9 |
| Full backend regression suite before final added driver regression | 245 passed, 1 skipped; 11 subtests passed |
| Existing skipped integration | RAG database test requires RAG_TEST_DATABASE_URL; not configured |
| Workspace + private-session PostgreSQL/PGlite tests | 18 passed, no skips |
| Full frontend suite | 100 passed, no skips |
| Runtime lint (agents/orchestrator/shared) | Passed |
| Frontend syntax and static build | Passed; twelve allowlisted public assets |
| git diff --check | Passed |

Python tests use a controlled transactional store and provider responses, including
two-manager refresh locking, UUID driver adaptation and outage-after-rotation.
PGlite executes actual migrations, grants, RLS and session SQL, with synthetic
Supabase Auth roles/schema. This verifies local behavior, not a live psycopg-to-
Supabase round trip, actual PostgreSQL replica concurrency or hosted role creation.
The full backend run reported dependency deprecation warnings without failures.

No actual browser/mobile/screen-reader, production Python 3.11 container build,
hosted provider/database, email or multi-replica acceptance was performed. No
commit, push, paid service, account upgrade or deployment created.

## Completion gates

Login/signup/resend/recovery/password exchanges and /auth/callback are not yet
implemented. Signed-out session inspection remains 401 (or 503 when unconfigured)
rather than enabling an unsupported anonymous login bootstrap. Complete provider
exchange/callback state and replay checks, rate limits, account-wide recovery
revocation and real email journeys. Configure the dedicated database login,
shared encryption secret, host/origins and Supabase settings. Run real replica,
refresh/crash recovery, RLS, browser and backup/restore acceptance.

The new boundary does not protect legacy /ask or specialist routes: production
ingress must keep those private, and client live integrations still require tenant
isolation. Workspace tools/persistence remain OPU-96/97. Do not mark OPU-95 Done
from local mocked/provider-policy tests alone.

See [setup and integration handoff](../docs/session-management.md).
