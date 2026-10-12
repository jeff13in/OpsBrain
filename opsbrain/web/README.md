# OpsBrain website preview (OPU-84 through OPU-91)

Two-engineer UI foundation on `joint`. The existing Python API, Groq/Gemini
configuration, Compose and transports are untouched. Demo mode works without a
backend; live chat and monitoring snapshots require the configured localhost API
gateway.

## Private hosted preview

The current static preview is deployed at
<https://opsbrain-private-preview.fluffyflea64.chatgpt.site>. Host access is
currently owner-only. The second approved engineer still needs to be added before
the two-person access criterion is complete. The hosted build is Demo-only: no
production same-origin API gateway or protected backend has been configured.

## Run locally

Requires Node.js 22 or newer. No package install, API key or backend is needed.
From `opsbrain/web/` in Windows PowerShell:

```powershell
npm.cmd run dev
# Open http://127.0.0.1:4173/
npm.cmd test
npm.cmd run check
npm.cmd run build
```

Use `npm` instead of `npm.cmd` on macOS/Linux. `npm.cmd` avoids Windows PowerShell
execution-policy restrictions without changing your security settings.
The preview binds only to loopback. Stop it with Ctrl+C. Set `OPSBRAIN_WEB_PORT`
to another port if 4173 is occupied. No account identity/access protection is
implemented; do not expose this development server through a public tunnel.

## Structure and visual language

- `public/`: HTML entry point, local SVG mark, CSS tokens, reusable template
  components and hash navigation. No third-party CDN, fonts or runtime calls.
- `scripts/`: Node-built-in static preview server and allowlisted build copy.
- `tests/`: component/safety checks, build smoke test and loopback HTTP tests.
- `dist/`: generated, allowlisted static output used by the private hosted
  preview. It contains no gateway or backend configuration.

Design: ink-green backgrounds, restrained lime accent, blue/purple/peach agent
identities, generous spacing, a responsive sidebar, text-labelled provenance
badges and readable system typography. Tokens live in `styles.css`; components
live in `ui.js`. Colors never carry availability meaning by themselves.
Keyboard focus, skip navigation, mobile menu/Escape handling, form labels,
status announcements and reduced-motion styles are included.

The interface kit demonstrates buttons, form input, Live/Demo/Disconnected
badges, loading, empty and error states. Its Live badge is an **example**, not a
health assertion. The draft checker validates text only; it neither sends nor
saves questions. The overview starts disconnected. Its selectable demo states use synthetic
fixtures and never claim successful backend connections or live metrics. Hash routes avoid server-side
rewrite requirements and work with static assets.

## Landing page (OPU-85)

The root URL now opens Home; `#/home` links directly to the landing page and
`#/dashboard` opens the workspace. Home explains the product, four specialist
agents, existing backend investigation flow and the current frontend limits.
Its example question is explicitly illustrative and does not execute a query.
Section links focus labelled destinations for keyboard users. All navigation is
hash-based, so direct landing/dashboard URLs use the same static entry file.

Hosting/access controls are supplied by the private host, not by this static
page. Local development has no identity check. The production same-origin API
and its independent protection remain pending in OPU-91.

## Safety and limits

The build copies exactly ten public assets, not the backend/environment tree.
Unknown existing build outputs cause a failure instead of deleting user files.
Never put provider keys, database credentials, access tokens or private
operational fixtures in `public/`. Environment/config copying is not supported.
Future frontend configuration must contain only public endpoint settings.
Chat questions, answers and sources render as escaped plain text. Markdown and
HTML are not interpreted; numbered citations focus local source entries.
The default development CSP blocks network connections (`connect-src 'none'`).
The optional localhost gateway permits same-origin requests (`connect-src 'self'`)
to four allowlisted routes. CORS and localhost checks do not replace backend
authentication. Dev-server security headers are not automatically
transferred to a static host. The document carries an interim CSP and referrer
policy, but OPU-91 must still configure and verify HTTP host protections.

Node tests check markup/hooks and HTTP behavior, not actual browser rendering,
screen-reader behavior or visual overflow. Manual browser QA is required before
hosted-preview acceptance. No production availability, private access or live
backend reachability is claimed by passing these foundation tests.

## Dashboard demo (OPU-86)

Open `http://127.0.0.1:4173/#/dashboard`, then use **Demo preview state** to
choose Populated, Partial availability, Loading, Empty, Error or Disconnected.
Direct links such as `#/dashboard?state=populated` select a preview state;
missing or unknown states default to Disconnected. Navigation state lives in the
URL only; the dashboard sends no backend requests. Completed chat conversations can
be saved locally by the History feature.

`public/demo.js` contains immutable, synthetic agent context, scalar signals and
example activity. Demo badges label the data; the backend always stays visibly
disconnected. Partial availability omits failed Code activity and preserves the
other sample results. Loading, empty, error and disconnected states show no
successful sample metrics. Error offers a **Reset demo preview** link, which
selects the populated fixture without retrying a network request.

The selector has a visible label, retains focus after state changes, and announces
the new state. Cards and signal grids adapt to narrow screens. History and optional live queries are described below. Real browser visual
and keyboard QA is still required before acceptance.

## Demo chat (OPU-87)

Open `http://127.0.0.1:4173/#/chat`, write a question (5–2000 trimmed
characters), choose a **Demo response scenario**, and select **Show demo answer**.
The question stays in this browser; completed conversations save locally. The selected scenario returns a fixed
synthetic answer independent of the question; no model or backend is called.
A short local delay displays a loading state and prevents duplicate submissions.

Scenarios cover a successful four-agent result, partial availability with Code
unavailable, and all agents unavailable. Answers keep numbered source references
alongside expandable per-agent results. Citation buttons scroll to and focus
the matching source. Sources are labelled synthetic text, not claimed external
links. Partial answers retain successful context and omit failed-agent sources;
all-failed responses contain no successful sources or diagnosis.

The renderer uses the backend response field names `status`, `answer`, `sources`
and `results`, but this is not a connected API adapter. Questions, answers,
source text and error messages are escaped. HTML and Markdown are plain text.

Up to 20 turns belong to each conversation. Completed turns save automatically
in this browser. **New conversation** resets the active chat while retaining its
saved history. Reopen or delete saved conversations from History. Unsubmitted
drafts may be discarded when navigating away. No backend session is implemented;
live integration is available through the optional gateway described below.

OPU-86 through OPU-90 are implemented and automated checks pass; they are **ready
for review**, with actual browser desktop/mobile, keyboard and visual QA pending.
This file records local delivery status; it does not update an external tracker.

OPU-91 is in progress. Frontend CI now covers the active collaboration branch;
hosted access, protected API configuration and browser acceptance are still
required before OPU-91 can be marked complete. Progress is recorded in the
[OPU-91 validation note](../validation/OPU-91.md).

## Demo monitoring (OPU-88)

Open `http://127.0.0.1:4173/#/monitoring`. The page starts Disconnected.
Choose **Populated** to load synthetic CPU utilization, memory utilization and
p95 response latency charts. Choose **Last 15 minutes** or **Last hour** to show
four or twelve samples at five-minute intervals. The hour fixture begins 55
minutes ago; there is no interpolation or query to a real monitoring service.

**Refresh demo** alternates two fixed sample sets after a short local loading
state. **Auto-refresh demo (30s)** is off by default and stops when navigating
away or hiding the tab. Returning requires enabling it again. Overlapping
refreshes are suppressed, option changes discard stale results, and leaving
while loading cancels acceptance of the pending snapshot. Controls and the most
recent completed snapshot remain in page memory until reload.

The displayed UTC generation timestamp describes the demo generation time,
not a backend observation. Relative chart times describe a synthetic window.
SVG charts include titles and descriptions, fixed percentage/millisecond axes,
and expandable tables of exact sample values.

Scenarios cover populated data, latency unavailable with CPU/memory retained,
empty, error and disconnected. Missing values never appear as zero or healthy.
Loading, error, empty and disconnected screens display no successful charts.
Refresh keeps the chosen scenario; choose Populated to leave an illustrative
error state. A preparation failure clears previous samples and stops automatic
refresh instead of substituting successful demo data.

Actual browser desktop/mobile, visual, keyboard and screen-reader review remain
pending. Live alert/pod snapshots are available in live mode; CPU/memory/latency charts
remain demo-only.

## Browser-local history (OPU-89)

Open `http://127.0.0.1:4173/#/history`. Completed demo conversations save
automatically under the browser storage key `opsbrain.demo-history.v1`.
**Open in chat** restores the questions, answers, sources and per-agent outcomes,
and allows continuing the same conversation. Only completed turns save; a pending
answer is not restored after reload. **New conversation** keeps saved history;
**Delete** and **Delete all history** remove saved records and clear an affected
active chat, including any pending response.

Each record expires 72 hours after creation, even if reopened or continued.
Expired records are rejected on access and removed from storage on reads,
navigation, tab visibility changes and minute checks while the page is visible.
Cleanup requires the website to run; a closed browser cannot delete data on a
timer. The latest 20 conversations (up to 20 questions each) are retained.
Dates are displayed as UTC timestamps. Stored data is validated and rendered as
escaped text, and demo provenance is retained.

History belongs to this browser profile and exact origin (host and port), with
no server sync, account protection or encryption. Storage failures switch to
page-memory history with a visible warning. Changes in that mode are lost on
reload, and previously saved disk data may remain if deletion cannot be written.
Malformed or oversized records are discarded safely. Operations read the current
owned storage key before changing it; storage events update other open tabs.
Simultaneous writes across tabs remain best effort because browser storage has
no transactional merge. No unrelated storage keys are touched.

## Local live API adapter (OPU-90)

Demo remains the default. To enable the localhost gateway on macOS/Linux, run
from `opsbrain/web/`:

```bash
OPSBRAIN_WEB_API=1 npm run dev
```

On Windows PowerShell:

```powershell
$env:OPSBRAIN_WEB_API = '1'
npm.cmd run dev
```

Use `http://127.0.0.1:4173/` (the gateway requires this literal loopback host).
The server-side defaults are `http://127.0.0.1:8000` for Orchestrator and
`http://127.0.0.1:8002` for Monitoring, matching Compose's host ports.
`OPSBRAIN_WEB_ORCHESTRATOR` and `OPSBRAIN_WEB_MONITORING` can select other literal
`http://127.0.0.1:port` origins. These settings are never bundled into client
assets. The gateway is disabled without `OPSBRAIN_WEB_API=1`.

Starting the preview does not start backend containers, read `.env` or send an
API request. **Connect live** checks Orchestrator health. Only then can **Ask live
API** submit a question. New conversation rotates the page-memory backend
session. **Disconnect** cancels active requests and clears page state; **Use demo**
is a deliberate transition, never an automatic failure fallback. Switching modes
starts a new chat and stops demo auto-refresh. Reopening demo History explicitly
returns to demo mode. Live conversations remain in page memory and cannot be
saved as demo history.

Gateway allowlist:

| Browser route | Upstream route | Method |
| --- | --- | --- |
| `/api/orchestrator/health` | `/health` | GET |
| `/api/orchestrator/ask` | `/ask` | POST (question query only) |
| `/api/monitoring/alerts/summary` | `/alerts/summary` | GET |
| `/api/monitoring/pods/health` | `/pods/health` | GET |

Unknown routes/methods, arbitrary upstream URLs, query parameters, cross-origin
requests and extra question fields are rejected. Cookies and authorization
headers are not forwarded. Requests have deadlines and size limits, redirects
are rejected, backend error prose is replaced with safe gateway messages, and
API response schemas are validated before rendering. Partial and all-failed
`AskResponse` results remain visible, including structured HTTP 502 responses.
Live reply text and sources remain escaped plain text. Health reachability does
not claim agent readiness or operational health.

Live Monitoring has manual **Refresh live snapshots** for alerts and pod-phase
counts. Failed snapshots remain unavailable alongside successful ones; no demo
chart is substituted. These are API retrievals, and the backend may itself use
demo exporters. CPU, memory and latency charts remain synthetic in Demo mode.
The static build contains the browser adapter, not this Node development gateway.
Hosted use requires a separately protected same-origin gateway/API and host CSP,
which belong to OPU-91; no production authentication is implemented here.

Automated local HTTP integration uses a contract-compatible test backend. Actual
backend/model connectivity and browser visual/keyboard QA remain to be verified.

## Interface refinements

Small UX improvements inside the existing demo/live architecture; they do
not replace the preserved live-readiness, time-series and account-history work:

- Chat composers show a live character count (`n / 2000`) and submit with
  Cmd/Ctrl+Enter in addition to the submit button.
- History has a client-side filter box that narrows the saved-conversation
  list and reports the filtered count (`shown of total / 20`).
- The live Overview shows the real API connection status message and
  whether a live session is active, instead of two bare links.
- The demo monitoring error state offers a Reset demo preview button that
  selects the populated fixture, matching the dashboard error state.

## Next website sprints

The reviewed backlog, dependencies and acceptance criteria are in the
[website sprint plan](../validation/website-sprint-plan.md).

1. OPU-91: private hosted preview, two-email access controls, frontend CI,
   connected-API protection and browser/end-to-end acceptance.
2. Week 5 / OPU-92–98: architecture, Supabase, authentication, protected client
   workspace, persistence and security/QA. See the
   [architecture contract](../architecture/client-workspace.md).
3. Week 6: the existing regression milestone and its 15 issues remain intact.
4. Preserved operational follow-ups (issue IDs unassigned): truthful live
   dashboard/readiness, bounded live time-series and account-scoped live history.
   The former proposed OPU-92–94 numbers now belong to the actual auth tickets.

The client release is an approved-client beta. Saved account work will remain
until the client deletes it; existing browser-local demo history still expires
after 72 hours. Authentication and account persistence are not implemented yet.
Client live operational access requires verified workspace isolation.
