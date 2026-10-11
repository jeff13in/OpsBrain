# OpsBrain website preview (OPU-84 / OPU-85 / OPU-86 / OPU-87 / OPU-88)

Local-only, two-engineer UI foundation on `joint`. The existing Python API,
Groq/Gemini configuration, Compose and transports are untouched. This is **not**
a deployed, authenticated website or a live chat/monitoring dashboard.

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
- `dist/`: generated static output, ignored by Git; suitable for static hosting
  only once the later hosting/access ticket is completed.

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

Hosting/access controls are not implemented by this page. The two-engineer
audience is an intended restriction, not a claim that authentication exists.
Continue to use localhost until OPU-91 verifies actual website/API protection.

## Safety and limits

The build copies exactly eight public assets, not the backend/environment tree.
Unknown existing build outputs cause a failure instead of deleting user files.
Never put provider keys, database credentials, access tokens or private
operational fixtures in `public/`. Environment/config copying is not supported.
Future frontend configuration must contain only public endpoint settings.
Chat questions, answers and sources render as escaped plain text. Markdown and
HTML are not interpreted; numbered citations focus local source entries.
The development CSP blocks network connections (`connect-src 'none'`). A future
API adapter must explicitly scope allowed secure endpoints; CORS does not replace
backend authentication. Dev-server security headers are not automatically
transferred to a static host: OPU-91 must configure and verify host protections.

Node tests check markup/hooks and HTTP behavior, not actual browser rendering,
screen-reader behavior or visual overflow. Manual browser QA is required before
hosted-preview acceptance. No production availability, private access or live
backend reachability is claimed by passing these foundation tests.

## Dashboard demo (OPU-86)

Open `http://127.0.0.1:4173/#/dashboard`, then use **Demo preview state** to
choose Populated, Partial availability, Loading, Empty, Error or Disconnected.
Direct links such as `#/dashboard?state=populated` select a preview state;
missing or unknown states default to Disconnected. Navigation state lives in the
URL only; the page sends no backend requests and saves no conversations.

`public/demo.js` contains immutable, synthetic agent context, scalar signals and
example activity. Demo badges label the data; the backend always stays visibly
disconnected. Partial availability omits failed Code activity and preserves the
other sample results. Loading, empty, error and disconnected states show no
successful sample metrics. Error offers a **Reset demo preview** link, which
selects the populated fixture without retrying a network request.

The selector has a visible label, retains focus after state changes, and announces
the new state. Cards and signal grids adapt to narrow screens. History and live integration
remain later tickets. Real browser visual
and keyboard QA is still required before acceptance.

## Demo chat (OPU-87)

Open `http://127.0.0.1:4173/#/chat`, write a question (5–2000 trimmed
characters), choose a **Demo response scenario**, and select **Show demo answer**.
The question stays in page memory. The selected scenario returns a fixed
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

Up to 20 turns remain in page memory during navigation. Reloading or **Clear
conversation** removes them. Clearing during loading discards the stale response.
No persistent history or backend session is implemented; those belong to OPU-89
and OPU-90. Unsubmitted drafts may be discarded when navigating away.

OPU-86 through OPU-88 are implemented and automated checks pass; they are **ready
for review**, with actual browser desktop/mobile, keyboard and visual QA pending.
This file records local delivery status; it does not update an external tracker.

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
pending. Live monitoring queries and response validation belong to OPU-90.

## Next tickets (in agreed order)

1. OPU-89: browser-local conversation history with 72-hour expiry.
2. OPU-90: read-only API adapter and deliberate demo/live transitions.
3. OPU-91: free hosted preview, two-email access controls, frontend CI,
   connected-API protection and end-to-end verification.
