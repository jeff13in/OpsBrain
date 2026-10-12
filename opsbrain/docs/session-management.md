# OPU-95 session foundation

Implemented locally October 12, 2026. No paid resources or hosted configuration
were created. This adds a protected client boundary alongside the existing
engineer API, rather than changing the local CLI/agent contracts.

## Session storage and identity

Apply the workspace migration, then
`supabase/migrations/202610120002_private_sessions.sql` to the application
Supabase database. It creates private `app_sessions`, RLS and a NOLOGIN
`opsbrain_session_store` capability with access only to that table. A deployment
administrator must provision a dedicated server database login and grant it this
capability. Do not give that login application-table, service-role, superuser or
other elevated memberships. Keep the private schema outside Data API exposure.
The migration has been tested locally; hosted role/migration permissions still
need verification. Preserve the existing operational RAG database.

The browser holds a random opaque 256-bit cookie. Only its SHA-256 hash is stored.
Access/refresh tokens are Fernet-encrypted together, bound to that session hash.
The production cookie helper sets __Host-opsbrain_session, Secure, HttpOnly,
Path=/ and SameSite=Lax without Domain. Explicit loopback development uses a
separate opsbrain_session_dev cookie. A shared private PostgreSQL store and the
same encryption key are required on every replica; no process-memory store is
available in production. The default lifetime is seven days absolute and
24 hours idle. Successful access touches idle time without extending absolute
expiry; expired/invalid sessions are deleted.

Protected requests fetch Supabase's user using the stored access token, rejecting
unverified, anonymous, deleted or currently banned identities. Workspace IDs
come from a publishable-key/user-Bearer Data API query governed by OPU-93 RLS.
They never come from browser ownership claims. Removal of beta eligibility or
membership removes access. The dedicated database login is used only for private
session storage, never ordinary workspace CRUD.

Refresh holds a PostgreSQL row lock and replaces the encrypted token pair in one
transaction. Successful rotation is retained if a following provider lookup is
temporarily unavailable, without extending idle time. Authentication remains
unavailable during the outage. Provider rejection revokes the session. A crash
between provider rotation and database commit remains a distributed failure
window requiring real provider recovery/reuse-window acceptance; local tests do
not establish crash recovery across live replicas.

## Environment

Provide APP_ENV, APP_ORIGIN, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY,
SESSION_ENCRYPTION_KEY (a Fernet URL-safe base64 key for 32 random bytes) and
SUPABASE_SESSION_DATABASE_URL through the server's secret manager. Use the
dedicated login with sslmode=require, verify-ca or preferably verify-full for
hosted environments. Origins must have no credentials, path, query or fragment;
HTTP is accepted only for explicit loopback development. Incomplete configuration
returns safe 503 responses and never enables a memory-backed fallback.

Use local development and available free staging/production project slots.
The private session table uses the same application PostgreSQL database, adding
no paid cache service. Coordinate encryption-key rotation across replicas;
single-key rotation currently invalidates existing sessions. Schedule deletion
of rows whose expires_at has passed or whose last_seen_at exceeds the idle limit.
Private session backups contain encrypted token material; protect backups and
the encryption key separately. Do not include tokens/DSNs in issue comments.

## Implemented endpoints and frontend

| Endpoint | Behavior |
| --- | --- |
| GET /api/auth/session | Revalidate identity/workspaces; return minimal verified state, membership IDs and session-bound CSRF, no-store |
| POST /api/auth/logout | Exact Origin plus constant-time CSRF check; delete application session before requesting provider local logout; clear cookie |
| GET /api/workspaces/{uuid}/session | Require identity and authorized membership; inaccessible IDs return 404; response is no-store |

The configured signed-out session endpoint returns anonymous 200 state, clears
the application cookie and issues a private CSRF flow cookie. The unconfigured
endpoint returns 503. Migration 004 and the dedicated auth-store capability are
required for credential exchange and rate limiting. No provider
token appears in endpoint responses. Logout revokes this application session
immediately even if provider logout fails; other devices are unchanged. Existing
provider access JWTs can remain usable until their independent expiry.

The browser's guarded #/workspace route resolves a verified server session before
showing client content. Anonymous/unverified users go to login/verification.
OPU-96 adds the workspace shell, authorized summary reads and embedded demo
tools after this gate; OPU-97 adds account persistence. A successful login response
now triggers a fresh session check before choosing an allowlisted destination
(Workspace or Home). Navigation/account logout clears protected page memory,
aborts requests and rejects stale replies. Logout clears the display before the
request completes and reports unconfirmed revocation on failure. Demo history
retains its existing separate browser-only behavior.

## Remaining release gates

Login/signup/resend/recovery/password exchanges and /auth/callback are now
implemented. Identity is revalidated before user-JWT provisioning; the session
manager derives identity and requires an authorized workspace. Recovery uses
encrypted server-only context, atomic one-time claims, account-wide local
revocation and provider-global logout. Verification consumes provider token hashes
and requires explicit login afterwards. Anonymous CSRF and atomic database auth
rate limits are implemented. See [account flows](account-authentication.md).

Complete OPU-93 provider/database/SMTP/host setup, OPU-94 live email acceptance,
OPU-96 hosted workspace acceptance and OPU-97 persistence. Verify real restart/replica refresh
races, provider outages, role grants, key rotation, backup/restore, email journeys,
browser/mobile and assistive-technology behavior. Production ingress must keep
old unauthenticated /ask and specialist routes private; this new boundary does
not protect arbitrary legacy endpoints. Shared live tools remain gated on tenant
isolation. Per user instruction, hosted acceptance belongs to the other engineer;
local completion does not authorize a client release.

Rollback the application deployment while retaining the additive schema and
private session data, disabling client ingress as needed. Do not reset/drop a
shared database. Restore only through the tested backup/restore plan in
[Supabase setup](supabase-setup.md).

References: [provider user verification](https://supabase.com/docs/reference/python/auth-getuser),
[provider refresh](https://supabase.com/docs/reference/python/auth-refreshsession),
[Fernet](https://cryptography.io/en/latest/fernet/),
[PostgreSQL transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).
