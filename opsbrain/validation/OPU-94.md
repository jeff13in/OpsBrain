# OPU-94 homepage/account UI increment

October 12, 2026. Local frontend implementation delivered; provider acceptance
remains pending. Keep this issue In Progress and preserve its OPU-93 dependency.

Added quiet homepage Log in and primary Sign up links; dedicated login/signup,
verification resend, recovery and new-password views; responsive styles matching
existing tokens; labelled fields/password-manager support, inline validation,
status announcements/focus, pending/disabled states and account navigation.

The new auth adapter uses fixed same-origin endpoints, cookie credentials, CSRF,
no-store, redirect rejection, deadlines and navigation cancellation. It never
persists passwords/provider tokens or puts them in snapshots. Server-owned
bootstrap/eligibility/recovery flags gate forms. Missing/malformed backend,
outages and invalid replies never produce fake account success. Callback/token
consumption and private-resource authorization remain backend/session work.

Updated the explicit asset allowlist and syntax checks for auth.js. The build now
contains eleven public assets. Existing demo/live/history behavior remains covered.

Verification: 92 frontend tests passed (77 existing plus 13 auth and 2 account
wiring tests); syntax checks passed; allowlisted build passed; git diff --check
passed. The initial sandboxed run could not bind localhost for three existing
HTTP tests; rerun with localhost permissions passed all checks without skips.
No Supabase/provider, actual browser visual, mobile, screen-reader or hosted
email acceptance was performed. Browser automation's required session tool is
not exposed in this environment; DOM/markup tests do not replace browser QA.

Affected implementation: web/public/auth.js, app.js, ui.js, styles.css;
web/scripts/files.mjs; web/package.json. Tests: auth.test.mjs, wiring.test.mjs,
ui.test.mjs and build-server.test.mjs. Documentation: frontend README,
docs/auth-ui-contract.md and this evidence. No new backend dependencies or
database objects in this increment. No hosted resources, paid services,
commit, push or deployment created.

See [backend handoff](../docs/auth-ui-contract.md) for required bootstrap/session,
resend and callback contracts. OPU-94 acceptance remains pending OPU-93's real
provider/SMTP setup and OPU-95's protected server sessions and callbacks.
