# OPU-84–91 implementation closeout — October 13, 2026

The user requested finishing these issues and adding sub-sprints as needed.
All eight issues are Done for their verified implementation scope. Original
acceptance requirements and prior review history are retained in Linear;
this is not full Week 4 release acceptance.

Fresh checks in `opsbrain/web`: `npm.cmd test` — 140 passed, zero failures/skips;
`npm.cmd run check` passed; `npm.cmd run build` passed, 17 allowlisted assets.
Tests include actual loopback HTTP transport with controlled backend responses,
not operational backend or browser acceptance.

## Requirement handoff

| Parent | Delivered scope | Remaining ticket |
| --- | --- | --- |
| OPU-84 | Visual system, navigation, state patterns, static build | OPU-175 browser/accessibility |
| OPU-85 | Product overview, agent explanations, accurate limits and navigation | OPU-175; hosted enforcement OPU-105 |
| OPU-86 | Labelled synthetic dashboard and failure/disconnected states | OPU-106 live readiness; OPU-175 |
| OPU-87 | Chat, citations, routing/latency, partial failures, safe plain text | OPU-176 Markdown/code blocks; OPU-175 |
| OPU-88 | Demo CPU/memory/latency charts, tables and refresh controls | OPU-107 real series plus request/error counts and availability; OPU-175 |
| OPU-89 | Demo-only browser history, last-message +72h expiry and deletion | OPU-177 Live retention/persistence decision and implementation; OPU-175 |
| OPU-90 | Explicit adapter modes, schema/cancellation guards, local gateway | OPU-105 actual backend/hosted acceptance; OPU-175 |
| OPU-91 | CI/build/setup and previously recorded private Demo preview foundation | OPU-105 hosted identity/API/headers/rollback; OPU-175 |

Created OPU-175 under OPU-91, OPU-176 under OPU-87 and OPU-177 under OPU-89.
Reused existing OPU-105/106/107 as children of OPU-91/86/88 respectively.
All follow-ups stay Backlog, assigned to Rifat in Week 4. OPU-107 now explicitly
preserves the original missing metric categories. No original requirement was
removed or converted into passing acceptance.

Comments and description closeout notes use Prompt Engineer's prompt-design
guidance: observable outcomes, evidence, explicit unknowns and testable acceptance.
Existing Week 5 account functionality is preserved; account persistence and
browser-local Demo retention remain distinct. Week 1–3 status was not changed.

Hosted setup remains deferred. No host audience/invitation/configuration change,
deployment, provider call, application-code edit, commit or push was made.
OPU-63 release review is not accepted by this administrative closeout.
