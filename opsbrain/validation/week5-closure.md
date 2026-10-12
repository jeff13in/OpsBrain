# OPU-92–98 local closure and OPU-99 hosted handoff

October 12, 2026 (America/Toronto). The user requested review/fixes of all seven
tickets so their implementation can be Done, then explicitly delegated hosted
project/host setup and acceptance: “The other engineer will work on it so for now
we have to skip that.” Closure is for the completed local implementation scope.
Original hosted acceptance requirements are preserved in
[OPU-99](https://linear.app/opusbrain/issue/OPU-99/week-5-hosted-setup-and-client-release-acceptance-engineer-handoff),
which remains an open release gate. No hosted acceptance is claimed.

## Review outcome

| Ticket | Local completion evidence |
| --- | --- |
| OPU-92 architecture/audit | Actual stack, individual owner model, environment/migration boundaries, documented deployment inputs, separate live isolation gate; implementation routes and current handoff reconciled |
| OPU-93 Supabase setup | Four ordered transactional migrations, scoped user-JWT data access, private session/auth roles and default-deny RLS; environment validation, migration/rollback/SMTP template handoff |
| OPU-94 account flows | Existing accessible account views now wired to implemented login/signup/resend/recovery/password APIs, generic acknowledgements, validation and server callback |
| OPU-95 sessions/routing | Opaque encrypted durable sessions, verified authorized routing, CSRF, expiry/refresh/revocation/account switching; durable anonymous and one-time recovery contexts |
| OPU-96 workspace UI | Existing six-section authorized shell, responsive rules, scoped summary/personalization, settings and Demo tools; same-origin client host serves all UI assets with live routes excluded |
| OPU-97 persistence | Existing project/profile/preferences/saved-work API/UI, optimistic versions, idempotency, quotas, deletion/tombstones; user-JWT verified provisioning integrated with login/callback |
| OPU-98 security/QA | Private success/error headers and redaction, shared auth throttles, restrictive client/static boundary, credential scan, required CI gates, regressions and release/rollback evidence |

## Gaps fixed in closure pass

- Missing backend account exchanges, anonymous bootstrap, verified onboarding,
  token-hash verification/recovery callbacks and password update are implemented.
  Provider tokens stay encrypted server-side. Verification requires explicit
  login; recovery cannot grant ordinary workspace access by itself.
- Migration 004 introduces private email-hash beta eligibility, durable auth
  contexts and atomic rate counters. User-JWT provisioning accepts no target ID.
  RLS denies currently banned/deleted/anonymous users even with an older JWT.
- Exact Origin/CSRF and strict 4-KiB account bodies are enforced; signup defaults
  disabled on both bootstrap and backend. Successful login rotates cookies and
  invalidates old application sessions. Recovery claims are one-time and revoke
  all local sessions before provider password/global logout operations.
- Separate `orchestrator.client:app` serves fourteen static allowlisted assets
  plus account/workspace APIs at one origin. Engineer `/ask`, metrics, API docs
  and specialists are excluded. Image copies only the fourteen UI assets.
  Server callback raw access logging is disabled in the image/host instructions;
  actual proxy/provider logs still require deployed verification.
- Database test workers are now isolated one suite per process with a 60-second
  timeout. A prior serial multi-file node worker stalled; only its identified
  processes were stopped. Both the isolated runner and final direct-file runner
  passed all four suites. No persistent client records were involved.
- Corrected current auth/session/workspace/setup documentation and added complete
  account setup, email templates, maintenance, release and rollback handoffs.
  Historical increment reports remain historical; this file supersedes their
  prior missing-backend and In Progress/In Review statements for local scope.

## Final local verification

| Check | Result |
| --- | --- |
| Full backend suite, Python 3.12.9 | 283 passed, 1 existing external RAG database test skipped; 11 subtests passed |
| Focused auth/session/security suite | 61 passed |
| Full frontend suite | 120 passed, no skips |
| Actual migration/RLS/persistence SQL suite | 37 passed across four isolated suites |
| Runtime ruff | Passed |
| Frontend syntax and static build | Passed; fourteen allowlisted assets |
| Public credential-pattern scan | Zero findings; heuristic only |
| Workflow parse/image gate dependencies | Passed |
| Diff whitespace and changed-document links | Passed |

Local account tests exercise signup→verification→login→save→logout→login→reopen,
resend/recovery, bad credentials/outages, Origin/CSRF/ownership/body denial,
throttling after restart, signup gate, cookie rotation, encrypted recovery,
account-wide revocation, recovery outages, expiry/replay and concurrent claim,
static allowlist and exclusion of legacy endpoints. Provider HTTP tests use
controlled transport; persistence uses controlled storage. SQL tests execute the
actual migrations/policies with synthetic provider Auth schema/roles. DOM tests
are not actual browser visual or accessibility acceptance.

The backend skip needs RAG_TEST_DATABASE_URL. Existing dependency deprecation
warnings did not fail checks. Frontend localhost integration tests required
authorized sandbox escalation. Production Python 3.11 images/remote CI and
actual provider concurrency are delegated and unverified.

## Remaining release work and material limits

OPU-99 tracks free hosted project/region/API host/SMTP, secret-manager and role
setup, installed email templates, actual end-to-end email/save/recovery,
two-account PostgREST isolation, replica/provider refresh behavior, desktop/mobile
and keyboard/screen-reader QA, measured latency/throttling, Python 3.11 images,
remote CI, safe proxy/provider logs, scheduled auth cleanup, capacity/receipt
maintenance and encrypted backup/restore/rollback evidence. No paid resources
were created. Shared client live integrations remain disabled.

Provider JWTs have independent expiry; provider-global logout revokes refresh
tokens and local recovery revokes application sessions immediately. A recovery
outage after password update can leave the new password applied while returning
unavailable; consumed context requires a fresh email. Single-key rotation
invalidates old encrypted sessions/flows. Indefinite saved-work retention is
unchanged; auth cleanup must not purge client records or deletion tombstones.

No hosted database was changed, no production deployment performed, and no
commit/push created. The handoff is unassigned because no engineer identity was
provided. Week 4 scope and Week 6's existing regression tickets are preserved.

Implementation references: [account flows](../docs/account-authentication.md),
[release/rollback](../docs/client-release-runbook.md),
[architecture](../architecture/client-workspace.md),
[persistence](../docs/workspace-persistence.md).
