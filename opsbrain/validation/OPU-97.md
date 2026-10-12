# OPU-97 workspace persistence increment

October 12, 2026. Local implementation delivered; keep In Progress pending
hosted acceptance. Preserve OPU-93/95/96 dependencies and the free-only budget.

## Delivered

- Versioned preferences and owner-private saved Demo investigations, with
  composite workspace/project FK, indexed RLS, immutable ownership and cascading
  deletion. Existing OPU-93 transactional/idempotent provisioning is preserved.
- User-JWT/RLS project create/list/read/update/delete and saved-work operations;
  paginated list/read API and a bounded CSRF/exact-Origin mutation API. Profile
  targets derive from verified identity; browser owner/permission fields fail.
- Transactional workspace RPC with SHA-256 request fingerprints, retry receipts,
  expected versions and deletion tombstones. Direct receipt/tombstone inserts are
  unavailable to clients; narrow private definer helpers write metadata only.
  Retry payload changes conflict; deleted IDs cannot be resurrected by old creates.
- UI project create/rename/delete, account profile/start-page/motion preferences,
  explicit account saves from completed demo chat, saved-investigation reopening,
  title updates, deletion confirmation, pagination, feedback and exact retries.
  Reopened account payloads are not copied into browser-local demo history.
- Retention until deletion, database quotas, child/account-closure cleanup and
  documented backup/release limits. No account retention-expiry job added.

## Verification

| Check | Result |
| --- | --- |
| Full frontend suite | 120 passed; no skips |
| Final focused persistence frontend suite | 6 passed |
| Full backend suite | 252 passed, 1 existing external RAG database test skipped; 11 subtests passed |
| Final focused auth/persistence API suite | 30 passed after final question validation |
| Database suite | Serial migration/RLS/persistence checks passed; final suite totals 28 tests |
| Runtime lint | Passed |
| Frontend syntax and static build | Passed; fourteen public assets |
| git diff --check | Passed |

The initial parallel three-file PGlite run stalled without results. Stopped only
its known local test processes, then serial execution passed. Database npm test
now uses --test-concurrency=1 for stable memory/resource use. SQL tests execute
actual migrations/RLS/RPC/constraints with synthetic provider Auth roles/schema.
They cover retry identity, stale versions, two-user access denial, cross-workspace
FKs, sources/provenance restoration, unknown preference keys, quotas, cascade/
tombstone deletion, metadata forgery denial and provider-account closure cleanup.

API/provider/browser state tests use controlled replies and DOM fixtures. The
full backend suite ran on Python 3.12.9; production Python 3.11/container, hosted
Supabase/PostgREST, real signup→save→logout→login→reopen, live replica concurrency,
browser/mobile/screen-reader and backup/restore acceptance remain unverified.
The RAG skip needs RAG_TEST_DATABASE_URL. Dependency warnings caused no failures.

Changed objects: public profile preferences/version/update columns; saved_work,
workspace_receipts, workspace_tombstones; RLS/grants, private quota/deletion/
receipt helpers and triggers, public workspace_mutate RPC. No hosted database
changed. No new dependency, paid service, commit, push or deployment created.

Implementation: orchestrator/auth/persistence.py, provider.py, sessions.py and
main.py; supabase/migrations/202610120003_workspace_persistence.sql;
web/public/persistence.js, route-guards.js, workspace.js, app.js, ui.js, styles.css;
asset/syntax/test-runner configuration. Tests: persistence.test.mjs in database
and frontend suites, test_auth_sessions.py, wiring.test.mjs and ui.test.mjs.

## Remaining release gates

Apply and verify staging migrations/role/schema exposure. Complete upstream
provider login/callback/host setup and real account journeys. Confirm initial
100-project/100-investigation/128-KiB/5,000-non-delete-receipt limits and maintenance
with the beta owner; authorized deletion remains allowed at the receipt limit.
No hosted backup window, encrypted export location/owner or restore evidence
exists yet. Account closure currently has verified FK cleanup semantics; its
provider/admin workflow still needs integration. Saved records are Demo only;
Live investigations stay behind tenant isolation. Keep OPU-97 In Progress until
these acceptance conditions are satisfied.

See [persistence contract and retention](../docs/workspace-persistence.md).
