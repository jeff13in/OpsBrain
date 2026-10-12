# Week 5 client release and rollback

OPU-98, October 12, 2026. Local verification is available; client staging and
production release are not ready. The user delegated hosted setup/acceptance to
the other engineer; [OPU-99](https://linear.app/opusbrain/issue/OPU-99/week-5-hosted-setup-and-client-release-acceptance-engineer-handoff)
tracks these remaining release gates separately from local OPU-92–98 completion.
Use local development and available free
resources only. No hosted resources were provisioned for this increment.

## Release inputs and scope

Record the commit/image digest, environment, application HTTPS origin, Supabase
project identifier/region, migration ledger, deployment owner, secret-manager
references and rollback image. Never copy secret values into Linear or evidence.
API hosting, SMTP/sender, hosted projects and backup owner/location/restore window
remain unselected. Existing EKS/ArgoCD workflow is inherited infrastructure;
these changes do not select it as the free client host or provision it.

Deploy frontend and API at the same origin. The local preview/gateway does not
forward account endpoints and is not a production client host. The new
`orchestrator.client:app` entry point serves only account/workspace APIs and the
static allowlist at one origin; use `--no-access-log`. Serve only the
fourteen allowlisted static build assets. Configure the static host with the
preview server's CSP, nosniff, no-referrer and no-store policy. HTTPS/HSTS belongs
at the hosting ingress. Verify actual deployed headers rather than relying on
the HTML CSP meta tag (which cannot enforce frame-ancestors).

Allow client ingress only to implemented `/api/auth/` and `/api/workspaces/`
routes. Keep legacy `/ask`, `/metrics`, docs/OpenAPI, specialist and administrative
endpoints private. They do not acquire tenant protection from account routing.
Shared client live integrations remain disabled pending isolation acceptance.

## Local checks and CI gates

Run from `opsbrain/` using the project's development environment:

```sh
ruff check agents/ orchestrator/ shared/
pytest tests/ -q
npm --prefix supabase test
npm --prefix web test
npm --prefix web run check
npm --prefix web run build
python3 scripts/check-public-secrets.py web/dist
```

GitHub image build/check and push jobs require successful Python, frontend and
database jobs. Deploy depends on image push. ArgoCD requests fail on HTTP errors
and timeout after 30 seconds. A successful sync request is not evidence that a
deployment is healthy; record the deployed digest and verify health separately.
Hosted client acceptance is separate from these local/CI gates.

The public scanner detects common private-key, secret-key, JWT, provider-key,
AWS-key, database-password and GitHub-token shapes. Output contains filenames
and rules, never matches. Zero findings is a heuristic result, not proof of
absence; review secret-manager separation and actual runtime/access logs too.
Publishable keys are allowed. Never put session encryption keys, session DSNs,
service-role keys, provider tokens or client passwords in public assets.

## Database and server setup

1. Identify the application database; preserve the separate operational RAG
   database. Export existing application schema/data to encrypted private storage
   and prove restoration to an isolated local database before hosted migration.
   Record retention, deletion and restore ownership; backups currently lack this
   configuration and evidence.
2. Check the migration ledger and apply each unrecorded migration in order:
   `202610120001_workspace_foundation.sql`,
   `202610120002_private_sessions.sql`,
   `202610120003_workspace_persistence.sql`,
   `202610120004_account_flows.sql`. Each file is transactional. Do not
   run already applied migrations as ad-hoc SQL.
3. Verify `opsbrain_private` is absent from exposed Data API schemas. Provision
   a dedicated server login with only `opsbrain_session_store` and
   `opsbrain_auth_store` capabilities.
   Verify anonymous/user/service roles cannot access private sessions and that
   the session login cannot read public client records or provision memberships.
4. Supply validated server settings from the secret manager: APP_ENV, APP_ORIGIN,
   SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SESSION_ENCRYPTION_KEY and
   SUPABASE_SESSION_DATABASE_URL with TLS. All replicas share the encryption key
   and durable store. Invalid configuration must fail closed with safe 503.
5. Deploy the implemented provider onboarding, approved-beta provisioning,
   anonymous CSRF, account exchanges, one-time recovery and shared rate limits.
   Install the two versioned email templates and configure exact callback
   allowlists/SMTP. BETA_SIGNUP_ENABLED defaults false. Follow
   [account setup](account-authentication.md) and verify real provider behavior
   before enabling the approved beta signup flow for clients.

Account APIs now apply no-store/no-cache, nosniff, no-referrer and restrictive
JSON CSP to successes, route errors, validation and pre-response unexpected
failures. Validation omits submitted values. Unexpected failures return generic
500 and log a constant message without exception content. Reverse proxy error
pages and access logs need their own deployed verification/redaction.

## Required staging evidence

Record date, deployed digest, environment and sanitized results for every row.
Use two separate approved accounts and an anonymous browser. Local fixtures do
not meet these gates.

| Gate | Required evidence | Current status |
| --- | --- | --- |
| Auth/onboarding | Signup, mail verification, verified retry provisioning, callback expiration/replay and allowlist denial | Backend exchanges/local journey pass; hosted setup pending |
| Save/resume | Workspace, Demo tool, create project, save sources/provenance, logout, sign in and reopen | Local fixtures pass; hosted journey pending |
| Direct API isolation | A cannot read/change B's workspace/records with changed path/body IDs; anonymous denied; forged owner/role denied | Local API fixtures pass; staging pending |
| Database isolation | Repeat direct PostgREST/RPC/table calls with two real user JWTs and anonymous role; verify column grants/private schema | Local actual SQL/RLS tests pass; hosted PostgREST pending |
| Sessions/recovery | Expiry/refresh across replicas, restart, concurrent refresh, provider outage, account switching, password reset revocation and link expiry | Local session fixtures pass; real provider/replicas/recovery pending |
| Deletion/retry | Retry identity, stale versions, quota behavior, child cleanup, tombstones and provider-account closure | Local SQL/API pass; hosted/admin workflow pending |
| Runtime security | Cookie attributes, CSRF/Origin denial, HTTPS/headers, safe logs, auth throttling, bounded error responses and request latency | Local boundary/shared throttle checks pass; ingress/provider behavior and hosted measurements pending |
| UX/browser | Desktop/mobile, keyboard focus/menu/forms, screen reader errors, navigation and private-state cleanup | DOM/markup fixtures pass; actual browser QA pending |
| Recovery operations | Backup restore, rollback/redeploy, key rotation and migration/role availability | Runbook available; operational evidence pending |
| Regressions | Python 3.11 service images, frontend build and CI results for deployed digest | Local Python 3.12 tests pass; image/remote CI pending |

Requests already have provider timeouts, response/body caps, bounded pages and
database record quotas and now atomic cross-replica authentication rate buckets.
These do not prove free-host capacity. Test per-account/IP limits at the actual auth ingress,
return safe 429/Retry-After, and measure provider/DB latency under concurrent
refresh and workspace operations. Do not enable signup before these checks.
Keep Week 6's broader regression work intact.

## Rollback and recovery

If isolation, migration availability or auth correctness fails, stop client
ingress at the host and disable signup/live access. Record the failed digest and
last known good digest. Restore that application/frontend version together;
retain the additive database schema, saved records, receipts and tombstones.
Do not delete tombstones/receipts to make a retry succeed. Confirm closed ingress,
legacy engineering regressions and safe account failure before reopening.

A failed migration rolls its transaction back: inspect the ledger and resolve
the failure before retrying. A committed schema is not reverted by rolling back
the application. If database restoration is necessary, restore an encrypted
backup into an isolated replacement, reconcile client writes since the backup,
verify RLS/grants/session denial and only then switch the application connection.
Never reset/drop a shared database. No destructive down migration is provided.

On suspected session-key compromise, close client ingress, revoke application
sessions and rotate the key consistently on all replicas through the secret
manager. Existing ciphertext becomes unreadable after single-key rotation;
users must sign in again. Provider-token revocation needs the provider workflow.
Test this recovery before release. Retain sanitized evidence and links in Linear;
OPU-99 remains the hosted release gate until those acceptance rows pass.
