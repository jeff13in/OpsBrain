# OpsBrain website foundation (OPU-84)

Local-only, two-engineer UI foundation on `joint`. The existing Python API,
Groq/Gemini configuration, Compose and transports are untouched. This is **not**
a deployed, authenticated website or a completed chat/monitoring dashboard.

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
saves questions. The overview shows all agents disconnected instead of inventing
successful backend connections or live metrics. Hash routes avoid server-side
rewrite requirements and work with static assets.

## Safety and limits

The build copies exactly five public assets, not the backend/environment tree.
Unknown existing build outputs cause a failure instead of deleting user files.
Never put provider keys, database credentials, access tokens or private
operational fixtures in `public/`. Environment/config copying is not supported.
Future frontend configuration must contain only public endpoint settings.
Template text is escaped; future Markdown chat needs its own sanitization tests.
The development CSP blocks network connections (`connect-src 'none'`). A future
API adapter must explicitly scope allowed secure endpoints; CORS does not replace
backend authentication. Dev-server security headers are not automatically
transferred to a static host: OPU-91 must configure and verify host protections.

Node tests check markup/hooks and HTTP behavior, not actual browser rendering,
screen-reader behavior or visual overflow. Manual browser QA is required before
hosted-preview acceptance. No production availability, private access or live
backend reachability is claimed by passing these foundation tests.

## Next tickets (in agreed order)

1. OPU-85: landing-page content and polish.
2. OPU-86: dashboard demo fixtures and states.
3. OPU-87: chat, citations and per-agent results.
4. OPU-88: monitoring charts and refresh controls.
5. OPU-89: browser-local conversation history with 72-hour expiry.
6. OPU-90: read-only API adapter and deliberate demo/live transitions.
7. OPU-91: free hosted preview, two-email access controls, frontend CI,
   connected-API protection and end-to-end verification.
