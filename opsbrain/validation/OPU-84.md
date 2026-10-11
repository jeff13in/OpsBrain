# OPU-84: website foundation and visual design

Implemented locally on `joint`, baseline `d55ee97`, 2026-10-11 UTC.
Entry point and commands: [frontend README](../web/README.md).

## Delivered

- Separate `web/` frontend: dependency-free HTML/CSS/ES modules, Node-built-in
  preview/build/tests. No package download or new backend runtime dependency.
- Ink-green/lime console design, local SVG identity, responsive sidebar and
  landing/dashboard navigation with labelled future-feature routes.
- CSS visual tokens, reusable cards/buttons/forms/icons and text-labelled
  Live/Demo/Disconnected/pending badges. Loading, empty and error examples.
- Keyboard focus, skip link, mobile menu/Escape handling, form labels and status
  announcements, responsive breakpoints and reduced-motion handling.
- Honest disconnected agent cards; component examples are not operational data.
  Draft validation sends/saves nothing. No model, API, credential or storage calls.
- Allowlisted five-asset static build; loopback-only read-only preview server
  rejects unknown paths, environment/backend files and non-GET/HEAD requests.
- Frontend setup, safety boundaries and next-ticket documentation.

The Sites workflow informed a local, static foundation without unnecessary
framework dependencies. Source registration/publication is intentionally deferred
to OPU-91, consistent with the ticket's local scope and two-engineer access gate.
The source contains no hosting identity or claimed access/authentication setup.

## Verification

From `opsbrain/web/`:

| Check | Result |
| --- | --- |
| `npm.cmd test` | 14 passed, no skipped/failed tests |
| `npm.cmd run check` | JavaScript syntax checks passed |
| `npm.cmd run build` | Five allowlisted assets produced in ignored `dist/` |
| `git diff --check` | Passed; Git line-ending warning only |

Tests cover route fallback/current-page semantics, disconnected agents, badges,
escaping, draft limits, accessible markup/hooks, core text contrast >= 4.5:1,
no client network/storage/credential calls, repeat builds, refusal to overwrite
unexpected build files and actual loopback HTTP asset/denied-path behavior.
Temporary test output and HTTP servers are created and cleaned by the tests;
no persistent preview server is left running.

## Verification limits and preserved flow

No browser-preview tool was available. Automated markup/token/HTTP tests are
not a substitute for real viewport, keyboard, screen-reader and visual QA.
Open the local preview and review desktop/mobile layouts before accepting the
foundation visually. OPU-91 still requires actual hosted access-denial testing.

Python services, Compose/Kubernetes configuration, model factory, routing,
embeddings and API contracts have no changes. Backend tests were not rerun for
this frontend-only task. No provider/backend call, ingestion, deployment, cloud
provisioning, secret edit, Git commit or push occurred.

Landing content (OPU-85), demo fixtures (86), working chat (87), charts (88),
72-hour history (89), live read-only adapter (90), and hosted two-email access
(91) remain separate tickets; placeholder routes do not count as their completion.
