# Account flows and engineer handoff

OPU-92–98 closure pass, October 12, 2026. The user delegated hosted Supabase,
same-origin hosting and acceptance to the other engineer. Implementation and
local controlled journeys are available; nothing in this document certifies a
hosted release. Everything must remain free.

## Run the client boundary

From `opsbrain/`, with the server environment configured:

```sh
PYTHONPATH=. uvicorn orchestrator.client:app --host 127.0.0.1 --port 8000 --no-access-log
```

This entry point serves the fourteen allowlisted UI files and account/workspace
APIs at one origin. It mounts no `/ask`, `/metrics`, specialist routes, API docs
or OpenAPI endpoint. Keep the legacy `orchestrator.main` engineer API private.
The orchestrator image includes frontend files; override its command to the
client entry point for the client host. Container/image acceptance remains the
other engineer's task. No additional paid service is required by this code.

Set APP_ENV, APP_ORIGIN, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY,
SESSION_ENCRYPTION_KEY and SUPABASE_SESSION_DATABASE_URL through the server's
secret manager. Use HTTPS outside explicit loopback development and database
TLS. Set BETA_SIGNUP_ENABLED=true only for the approved-email beta flow after
environment setup; the default is false and the backend independently enforces
it. A flag never grants workspace membership or live access.

Apply migrations 001–004 in order to the application database. Do not alter
already applied migration files or apply them to the separate RAG database.
Migration 004 adds `beta_invites`, `auth_flows`, `auth_rate_limits`, the
`opsbrain_auth_store` capability, and `ensure_personal_workspace()`.
The dedicated backend login needs both `opsbrain_session_store` and
`opsbrain_auth_store`; it may read invitations but cannot modify them, approvals,
public client records, provider accounts or administrative memberships.
Keep `opsbrain_private` outside exposed Data API schemas.

An administrator manages beta_invites using SHA-256 of the trimmed lowercase
email, computed in private tooling. Signup/resend consult that allowlist and
return generic acknowledgement for ineligible addresses. Verified user-JWT
onboarding checks the provider-owned email and invite hash, records the approved
user UUID and invokes the existing idempotent personal-workspace transaction.
It accepts no target-user argument and uses no service-role key in account
requests. Pre-existing UUID-based beta approvals remain supported for login.
To revoke a beta identity permanently, remove both its invite hash and UUID
approval; otherwise a still-invited verified user can re-provision approval.
The RLS approval helper also denies current banned/deleted/anonymous identities
even when an older provider JWT remains cryptographically valid.

## SMTP and links

Use the provider-supported token-hash email flow. Configure the project Site URL
to APP_ORIGIN, exact callback allowlist to APP_ORIGIN/auth/callback, email
confirmation enabled, compatible password rules and free SMTP/sender settings.
Install `supabase/templates/confirmation.html` and `recovery.html` as the provider
email templates. Do not use the default implicit token-fragment redirect: hash
fragments do not reach FastAPI. These templates have not been installed remotely.

The callback accepts exactly token_hash and type=email or recovery, sends the
hash to the fixed provider `/auth/v1/verify` endpoint, and redirects immediately
to a fixed internal hash view. Duplicate/unknown parameters, expiry, replay and
unsupported types do not grant a new context. Provider verification enforces
one-time use. Verification provisions only the verified approved identity,
revokes its temporary provider session, and returns to Login without silently
switching the browser account. Recovery clears the browser application session
and issues a separate encrypted, at-most-fifteen-minute recovery context.

Disable raw URL access logging at the host/proxy as well as uvicorn; callback
queries contain sensitive one-time hashes. Account middleware sets no-store,
nosniff, no-referrer and restrictive JSON CSP, including callback redirects.
Application errors log a constant message instead of provider bodies or input.
Verify actual host/proxy/provider logs separately; do not run credential debug
logging. The public credential-pattern scanner is heuristic, not proof that all
runtime logs or encodings are safe.

## CSRF, throttling and recovery

Anonymous bootstrap creates an opaque HttpOnly/Secure/SameSite=Lax flow cookie
(`__Host-opsbrain_flow`; explicit loopback has a distinct development name).
Only its SHA-256 hash is stored. CSRF uses a separate flow-specific HMAC purpose,
so it cannot replace an application-session CSRF token. Every account mutation
requires exact Origin and the proper context token; bodies are capped at 4 KiB,
extra ownership/redirect fields are rejected and passwords never enter responses.
Authenticated account switching can use the existing valid session CSRF token;
successful login rotates the cookie and revokes the old application session.

Rate counters live in PostgreSQL and survive process restarts. Each action has
100 attempts/minute globally, 20/minute per peer IP, and credential/email actions
share 5 attempts/15 minutes per normalized email (recovery password uses user ID).
Keys are HMAC hashes; addresses/IPs do not appear in counters. Atomic upserts
commit rejected attempts and safe 429 responses include the window's Retry-After.
Provider 429 is preserved. These are initial beta limits, not measured free-host
capacity. Configure only trusted ingress proxy addresses; spoofable forwarded
headers must not determine peer identity. Verify actual provider/IP quotas and
latency; frontend account requests currently have a ten-second deadline.

Password update atomically consumes the recovery row before using it. It derives
identity from encrypted provider tokens, revalidates it, revokes every local
application session/recovery context for that user, updates the provider password
and requests provider-global logout. Success clears cookies and requires login.
A provider/database outage after claiming the row cannot replay it; request a
new reset link. If password update succeeded before a later logout failure, the
response can be unavailable while the new password already applies. Existing
provider access JWTs have independent expiry; global logout revokes refresh tokens,
not every already-issued access JWT immediately. Local application sessions are
revoked immediately. Preserve this distinction in support/runbook wording.

Schedule free server maintenance hourly using the same private environment:

```sh
PYTHONPATH=. python scripts/cleanup-auth-state.py
```

It removes expired anonymous/recovery rows, old rate buckets and expired/idle
application sessions. It does not expire account projects/investigations or
remove retry tombstones. No scheduler was provisioned. Coordinate key rotation
across replicas; changing the single encryption key invalidates old sessions and
flows and requires a new login/reset email.

## Verification boundaries

Local tests run the real API routers, session manager, cookie/CSRF checks,
callback/recovery logic, strict inputs, static host and provider HTTP payloads
against controlled Auth/storage replies. SQL tests execute all four migrations
in PGlite with synthetic provider Auth schema/roles, checking role restrictions,
verified invite provisioning, bans, recovery claims, rate counters and cascades.
The save/logout/login/reopen journey is local fixture evidence; it does not prove
actual SMTP, PostgREST, replica races, backup restore or browser accessibility.
Those release checks belong in the other engineer's hosted handoff.

Provider contracts checked against [Auth OpenAPI](https://github.com/supabase/auth/blob/master/openapi.yaml),
[server-side email templates](https://supabase.com/docs/guides/auth/auth-email-templates)
and [global logout semantics](https://supabase.com/docs/guides/auth/signout).
