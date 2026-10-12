# OPU-90: read-only API adapter and demo/live transitions

Implemented locally, 2026-10-11. Status: **ready for review**, pending actual
backend and browser acceptance. Setup: [frontend README](../web/README.md).

## Delivered

- Explicit Connect live / Use demo / Disconnect controls. Demo is the default;
  Orchestrator health must succeed before live question submission is enabled.
  Health reachability is distinguished from agent readiness.
- Browser adapter for questions, alert summaries and pod health, with deadlines,
  cancellation, response-size/schema checks and safe failure behavior. Question
  responses validate aggregate/per-agent statuses and successful source ownership.
- Live chat renders API answers, citations and per-agent partial/failure results,
  including valid all-failed HTTP 502 bodies. Questions use a page-memory session;
  new conversations rotate that session. Responses render as escaped plain text.
- Mode switches clear active chat, cancel pending requests and stop demo refresh;
  late completions cannot overwrite the new mode. No automatic demo fallback.
  Live monitoring has manual alert/pod snapshots, preserving partial availability.
  CPU/memory/latency charts remain explicitly demo-only.
- Live conversations are kept in page memory and excluded from demo History.
  Opening a saved demo conversation explicitly returns to demo mode.
- Optional localhost Node gateway, disabled by default, with exactly four
  allowlisted read/query routes. Only literal loopback upstream origins are
  accepted. Host/origin checks, bounded JSON input/output, endpoint/method
  restrictions, no redirects, no cookie/auth forwarding and safe error responses.
- Default CSP still blocks connections; gateway-enabled preview allows only
  same-origin connections. Ten public build assets include the browser adapter;
  the Node gateway stays outside static build output.

## Verification

| Check | Result |
| --- | --- |
| `npm test` | 63 passed, no skipped or failed tests |
| `npm run check` | JavaScript syntax checks passed |
| `npm run build` | Ten allowlisted assets produced |
| `git diff --check` | Passed |

Nine new tests cover explicit health/session requests, cancelled/failed connection
checks, malformed/inconsistent answers and structured 502, live failure behavior,
stale chat completion suppression, partial monitoring, escaped live provenance,
gateway route/Host/origin restrictions, real local adapter-to-gateway HTTP flow
against a contract-compatible test backend, and live-history exclusion.

## Remaining acceptance and limits

Actual configured backend/model connectivity and real browser desktop/mobile,
keyboard, visual and screen-reader QA remain pending. The HTTP integration test
uses a test backend, not operational services. API retrieval can include backend
demo exporters and does not prove a real cluster connection.

The local gateway does not implement authentication. Static hosting requires a
protected same-origin gateway and independently protected API; OPU-91 owns that
work, host security headers, frontend CI and hosted end-to-end verification.
Provider settings, Python services, Compose, environment files and infrastructure
are untouched. No backend startup, provider query, deployment, commit or push.
No external issue-tracker status change. Next: OPU-91.


## Rifat’s assigned-scope follow-up — October 12, 2026

See [local fixes and current acceptance](week4-rifat.md): history retention now
uses last-message updates per OPU-89; API/chat preserve safe routing/latency;
late answers cannot survive session/connection changes. All 122 frontend tests,
syntax/build checks and the public credential-pattern scan pass. Prior
implementation/results above are historical; browser/hosted gates remain open.
