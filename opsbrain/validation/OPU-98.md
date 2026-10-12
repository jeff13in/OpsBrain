# OPU-98 security, QA and deployment readiness

Current closure: local implementation is complete under the user-directed
handoff. Hosted setup and release acceptance are tracked separately in OPU-99.
See [final cross-ticket evidence](week5-closure.md). The report below records
earlier increments and does not define the current completion scope.

October 12, 2026. Local implementation delivered; hosted acceptance remains
pending. Free-only budget preserved; no hosted apply, paid resource, push or
deployment performed.

## Delivered

- CI image build/check and push now depend on backend, frontend and migration/RLS
  gates. Deployment remains dependent on image push. ArgoCD HTTP failures and
  30-second timeout fail the job; secret values use environment variables.
- Account API response policy covers success, denial, routing/validation errors
  and unexpected failures before response start. Private responses cannot be
  cached; nosniff, no-referrer and restrictive JSON CSP are enforced. Validation
  input is omitted and unexpected exceptions return generic 500 with constant
  logs. Legacy API behavior is preserved.
- Heuristic public-build credential scan added to CI with value-free output,
  failure for empty builds and tests for seven credential families. A clean scan
  is not a full repository/runtime-log audit.
- [Release and rollback runbook](../docs/client-release-runbook.md) records exact
  migrations, restricted role/ingress setup, environment inputs, staging matrix,
  backup/restore, additive-schema rollback and session-key rotation limitations.

## Verification

| Check | Result |
| --- | --- |
| Full backend suite (Python 3.12.9) | 267 passed, 1 existing external RAG database test skipped; 11 subtests passed |
| Full frontend suite | 120 passed, no skips |
| Actual migration/RLS/persistence suite | 28 passed, serial PGlite execution |
| Focused security and auth suite | 45 passed |
| Runtime ruff, frontend syntax and build | Passed; fourteen assets |
| Public credential-pattern scan | Zero findings |
| Workflow YAML and dependency graph | Parsed; both image jobs require all three gates |
| git diff --check | Passed |

The first frontend run encountered sandbox EPERM on three localhost socket
checks; rerunning with authorized localhost access passed all 120 tests.
The backend skip requires RAG_TEST_DATABASE_URL; existing deprecation warnings
did not fail checks. Added 15 security checks
cover private success/error headers, redacted validation/provider errors,
production middleware registration, preserved legacy validation, scanner
detection without value disclosure and empty/public-key scan behavior.

These checks do not establish hosted signup/SMTP/callback/recovery behavior,
real browser/mobile/screen-reader QA, production Python 3.11 images, remote CI,
PostgREST or replica refresh/restore behavior. The auth exchange endpoints and
auth rate limiting are still missing upstream. Keep OPU-98 In Progress and
client live integrations disabled pending real tenant-isolation evidence.

Changed files: `.github/workflows/ci-cd.yml`, `orchestrator/main.py`,
`orchestrator/auth/security.py`, `scripts/check-public-secrets.py`,
`tests/test_account_security.py`, this evidence and the release runbook.
No database objects or new dependencies changed.
