# OPU-96 client workspace UI evidence

Current closure: local implementation is complete under the user-directed
handoff. Hosted setup and release acceptance are tracked separately in OPU-99.
See [final cross-ticket evidence](week5-closure.md). The report below records
earlier increments and does not define the current completion scope.

October 12, 2026. Local UI/read-only integration delivered; keep In Progress
pending hosted acceptance. OPU-95 dependency remains intact. Free-only budget
preserved; no account upgrade or paid resource created.

Implemented authenticated client sidebar/top-bar context, account menu,
personalized dashboard and six main sections: Dashboard, Software tools,
Projects & saved work, Recent activity, Account settings and Help & support.
Added loading, empty/error/retry states and explicit feature-availability copy.
Native details/summary, the existing mobile menu/skip link and focus behavior
support keyboard navigation; CSS adapts the shell/cards/details to narrow widths.

Embedded existing demo chat, monitoring and history controllers within client
subroutes. Client entry disconnects the live engineer adapter; client views offer
no live connection controls. Demo provenance/browser retention remain explicit.
Authenticated project/profile information comes from a new read-only summary
endpoint using verified membership and provider user-token/RLS queries. Scope,
field/count/date bounds and private-state cancellation are tested. Names/titles
are escaped; no static fake personalization is substituted for errors.

Verification:

| Check | Result |
| --- | --- |
| Full frontend suite | 113 passed; no skips |
| Full backend suite | 250 passed, 1 existing external RAG database test skipped; 11 subtests passed |
| Runtime lint | Passed |
| Frontend syntax/build | Passed; thirteen allowlisted public assets |
| git diff --check | Passed |

Tests include six section routes, client demo chat without network agent calls,
monitoring/history wiring, personalization/retry, cross-workspace/profile mismatch
denial, malformed/oversized policy bounds, escaping, cancellation and existing
engineer regressions. Provider replies and DOM are controlled fixtures. The RAG
skip requires RAG_TEST_DATABASE_URL. Backend ran on Python 3.12.9; the production
Python 3.11 container was not built. Existing dependency warnings had no failures.

Actual hosted Supabase, signed-in browser/mobile visual, screen-reader and
cross-client end-to-end acceptance were not performed. Browser automation's
required session tool is not available in this environment. No commit, push or
deployment performed. No database objects, backend dependencies or writes added.

Affected runtime: web/public/workspace.js, app.js, ui.js, styles.css, index.html;
web/scripts/files.mjs and package.json; orchestrator/auth/provider.py, sessions.py
and routes.py. Tests: workspace.test.mjs, wiring.test.mjs, ui.test.mjs and
test_auth_sessions.py. Documentation: frontend README, session handoff,
docs/client-workspace-ui.md and this evidence.

Profile/preference editing, project writes, saved work and complete activity feed
remain unavailable pending OPU-97. Live operational integrations remain gated.
OPU-93/94/95 provider/host/login/callback acceptance must complete before OPU-96's
authorized client landing and real browser criteria can be marked Done.
