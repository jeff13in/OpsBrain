# OPU-94 account UI and backend handoff

The frontend views/adapter are implemented. Backend endpoints described here
remain to be integrated with Supabase and the OPU-95 server-session work. These
responses are a contract, not proof that accounts or emails work today.

OPU-95 now implements authenticated session inspection, logout and a protected
workspace session endpoint. Signed-out requests currently return 401 when
configured, or 503 when setup is incomplete. The anonymous 200 bootstrap below
remains a required login/email-exchange handoff, rather than enabling unsupported
credential submission. Login/signup/resend/recovery/password/callback endpoints
are still pending provider integration. See [session management](session-management.md).

## Bootstrap

Only account-route visits and an explicit retry request `GET /api/auth/session`.
Return HTTP 200 JSON for an available account service, including a signed-out
visitor. This is the exception to the general protected-resource 401 rule:

```json
{
  "authenticated": false,
  "signup_enabled": false,
  "recovery_allowed": false,
  "csrf_token": "server-generated-base64url-token-at-least-32-characters"
}
```

All flags must be booleans. CSRF must contain 32–256 base64url characters and be
bound to the anonymous or authenticated server session. Return only necessary
account state and no provider access/refresh tokens. Use Cache-Control: no-store.
An absent, failed or malformed bootstrap disables all credential submissions.
The bootstrap's `authenticated` flag is display state; it does not authorize
access to private workspace records or shared operational integrations.

The user-approved beta policy remains in force. `signup_enabled` allows the
approved-beta signup flow; the backend must independently enforce identity
eligibility and verification. `recovery_allowed` must come from validated,
one-time provider recovery context, never a browser query/fragment/claim.

## Mutations

All requests are same-origin POST JSON, with credentials: same-origin,
X-CSRF-Token, no-store and redirect: error. The backend must validate CSRF and
exact Origin, enforce rate limits and reject unauthorized context. The frontend
never supplies upstream origins, callbacks, ownership or redirect destinations.

| Endpoint | Body | Success message |
| --- | --- | --- |
| `/api/auth/login` | email, password | Signed in; private routing is OPU-95 work |
| `/api/auth/signup` | email, password | Generic eligible-address check-email acknowledgement |
| `/api/auth/resend` | email | Generic verification-email acknowledgement |
| `/api/auth/recovery` | email | Generic reset-email acknowledgement |
| `/api/auth/password` | password | Password updated; log in again |

Success is HTTP 200 with `{"ok": true}`. The adapter never displays raw response
messages. Normalize duplicate signup and unknown resend/recovery addresses to
generic acknowledgements, preventing account enumeration. Login 401 gives a
generic credential failure; 429 asks the user to wait. Expired session/link 401
or 403 disables further submissions and offers a fresh-link/retry path. Provider
outages, invalid JSON and other failures show a generic availability message.
Set cookies before login success; enforce password validation server-side too.
After a successful mutation the adapter requires a fresh bootstrap before
another submission, permitting server session/CSRF rotation. OPU-95 now checks a
fresh verified session after login success before directing the user to Workspace
or Home; arbitrary post-login destinations are rejected.

The request deadline is ten seconds. Duplicate submits are suppressed.
Navigation aborts requests and invalidates late results. Password fields are
recreated empty during state updates; only email/validation messages are retained
in page memory. Response JSON is accepted only within an 8,192-character bound.

## Verification and recovery links

Emails must target the real same-origin server path `/auth/callback`, with the
provider-supported verification/recovery flow, expiry/replay checks and internal
redirect validation. The backend consumes sensitive parameters and redirects to
an account view only after clearing the URL. The browser does not consume provider
tokens from hash routes. Cross-device verification may then require login.
The verification view lets a user request a fresh email; it does not claim that
opening the view itself verified an account.

## Acceptance still required

OPU-93 provider/SMTP setup and OPU-95 session/callback handling must be completed
before end-to-end account acceptance. Test real approved signup, duplicate signup,
verification/resend, invalid login, expired/replayed links, cross-device recovery,
password update/session revocation and server-origin/CSRF enforcement. Run actual
desktop/mobile, keyboard and screen-reader checks. Current tests use controlled
responses and DOM fixtures; no hosted provider or real browser has been certified.
The free-only infrastructure constraint applies to this work.
