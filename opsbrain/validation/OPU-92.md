# OPU-92: Week 5 architecture and project audit

Current closure: local implementation is complete under the user-directed
handoff. Hosted setup and release acceptance are tracked separately in OPU-99.
See [final cross-ticket evidence](week5-closure.md). The report below records
earlier increments and does not define the current completion scope.

Date: October 12, 2026 (America/Toronto). Baseline:
`a6e2fc8843e0bf20b4dc2c7ea794b87c32195331` on `joint`.
Status: audit deliverables ready for review; deployment decisions remain open.

## Deliverables

- [Client workspace architecture](../architecture/client-workspace.md): actual
  stack, session/auth contracts, callbacks, data relationships, provisioning,
  RLS rules, environment/dependency plan and client live-access isolation gate.
- User confirmed approved-client beta access and client saved-work retention
  until explicit deletion. Demo history keeps its existing 72-hour behavior.
- [Roadmap](website-sprint-plan.md), root README and frontend README now use
  OPU-92–98 for the actual authentication/workspace tickets. Original live
  readiness, time-series and live-history work remains as named, unassigned
  follow-ups rather than conflicting with allocated IDs.
- Week 4 scope remains intact. Existing regression work remains Week 6 with
  its 15 existing issues; its milestone target is October 16. Week 5 dates and
  the historical project target still require calendar reconciliation.

## Issues fixed in this increment

1. Connection controls rendered on Home, Chat, Monitoring, History and Interface
   kit, but only Overview attached their handlers. Moved handler registration
   outside the Overview-only block while preserving its focus behavior. A new
   regression exercises controls on every route and switches Demo → Live →
   Disconnected from non-Overview pages.
2. Preview startup always claimed no backend was connected even when the local
   gateway was enabled. The message now reports gateway enablement and asks the
   user to check reachability explicitly; it does not infer backend health.
3. The local roadmap and entry-point README files assigned OPU-92–94 to different
   proposed work than the actual Linear tickets. Corrected references without
   deleting any original operational follow-up requirements.

Changed implementation files: `web/public/app.js`, `web/scripts/dev.mjs`,
`web/tests/wiring.test.mjs`. Changed documentation: root README,
`web/README.md`, `validation/website-sprint-plan.md`, this evidence note and
`architecture/client-workspace.md`. No database objects or dependencies changed.
The pre-existing untracked `.vscode/` directory was left untouched.

## Verification

| Check | Result |
| --- | --- |
| Baseline frontend test/syntax checks | 76 passed; syntax checks passed |
| Regression before fix | New wiring test failed: Home Connect live had no handler |
| Focused wiring test after fix | 9 passed, including non-Overview reconnect/disconnect |
| Full frontend suite after fix | 77 passed, no failures or skips |
| Frontend syntax checks | Passed |
| Static build | Passed; ten allowlisted public assets |
| Startup/HTTP smoke | Demo and enabled-gateway startup report correct modes; all ten assets return 200 in each mode |
| Local documentation links | 19 targets exist; external URLs and heading anchors excluded |
| `git diff --check` | Passed |

These tests include mocked browser/DOM interaction and local HTTP contract tests.
They do not certify actual browser visual/accessibility acceptance, production
hosting, Supabase authentication, database RLS or tenant-safe live integrations.
Python resolves only to an unusable WindowsApps execution alias in this session;
no runnable Python interpreter was found through PATH or the standard per-user
installation directory. Python regressions were not run. No Python runtime code
was changed and no interpreter/dependency was installed to work around this.

## Remaining issues and next owners

- OPU-93: choose Supabase project/region/budget, API-capable origin/host, private
  session store, migration tooling and SMTP configuration; no credentials are
  supplied in this checkout.
- OPU-94/95: implement auth and protected routes. Current local APIs are still
  unauthenticated and the gateway is not production authentication.
- OPU-97: transactional provisioning, projects/preferences/saved-work CRUD,
  user-scoped policies and deletion/backup semantics for indefinite retention.
- OPU-98: actual hosted browser/security acceptance, regression, delivery and
  rollback checks. OPU-91's separate private-preview gate is still incomplete.
- Separate live-integration gate: scope RAG retrieval/ingestion, conversation
  memory, monitoring/cloud/repository settings and HTTP/Kafka identity. Keep
  shared live sources unavailable to clients until that evidence exists.
- Calendar/capacity, approved beta identities, storage quota and backup window
  need real owner decisions. The audit documents these gaps rather than claiming
  they were configured or agreed.

No Supabase provisioning, auth/workspace implementation, production deployment,
commit or push was performed. OPU-92 should remain In Review until its contract
and outstanding architecture/calendar decisions are accepted.
