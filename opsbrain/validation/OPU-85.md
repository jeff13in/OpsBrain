# OPU-85: OpsBrain landing page

Implemented locally on `joint`, baseline `b7aa94d`, 2026-10-11.
Setup: [frontend README](../web/README.md).

## Delivered

- Home is the default entry point, with a product introduction and dashboard links.
- Four specialist explanations distinguish backend capabilities from required
  repository, cluster, knowledge-base and monitoring configuration.
- An explicitly illustrative question map and a three-step workflow explain
  routing, specialist execution and results with sources; neither executes a query.
- Current-scope panels distinguish implemented backend work from the frontend
  features still planned. No invented live health, adoption or performance claims.
- Landing section links have allowlisted targets and keyboard focus handling.
  Responsive layouts inherit the existing visual tokens and reduced-motion rules.
- The audience is two engineers. Copy explicitly states that deployment and
  access protection are not implemented; use localhost until OPU-91.

The Sites presentation-led guidance shaped the visitor progression: product
purpose, concrete illustrative question, specialist responsibilities, workflow,
current limitations and dashboard entry. Hosting remains deferred to OPU-91.

## Verification

From `opsbrain/web/`:

| Check | Result |
| --- | --- |
| `npm.cmd test` | 22 passed, no skipped or failed tests |
| `npm.cmd run check` | JavaScript syntax checks passed |
| `npm.cmd run build` | Five allowlisted static assets produced |
| `git diff --check` | Passed |

Eight added landing tests cover the default route, specialist descriptions,
honest illustration and access labels, navigation targets, section allowlisting,
semantic headings, labelled sections, static metadata and responsive CSS rules.
Existing tests still cover actual loopback HTTP serving, build safety and the
absence of client network, storage and credential calls.

## Remaining review and unchanged scope

Real browser desktop/mobile, keyboard and visual QA have not been performed:
no browser-preview tool was available. Automated markup and CSS assertions do
not establish visual or assistive-technology acceptance. Review locally using
`npm.cmd run dev`, then open `http://127.0.0.1:4173/#/home`.

No backend/model, API contract, Compose, credential, database or hosting changes.
No provider requests, deployment, commit or push. Dashboard demo data is OPU-86;
chat, charts, history, API integration and protected hosting remain separate work.
OPU-85 is ready for review, not claimed as fully accepted or deployed.
