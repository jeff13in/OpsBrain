# Rifat's Week 4 implementation and remaining acceptance — October 13, 2026

Linear `me` resolves to Rifat in OpusBrain. All 20 assigned Week 4 issues were
inventoried, including children. Thirteen were already Done. This pass implements
OPU-106, OPU-107 and OPU-176 locally; four acceptance/integration issues remain.

## Delivered

- OPU-106: fixed-target local health aggregation for Orchestrator/RAG/Monitoring/
  Infra/Code, redacted reachable/unavailable/unconfigured results, explicit unknown
  dependency readiness, retrieval timestamps, manual refresh and stale failures.
- OPU-107: server-owned CPU/memory/p95/request/server-error/availability queries
  through the existing Monitoring API; bounded 15m/1h windows, 60s steps, one
  aggregate series/61 samples per metric and 200 KB upstream response limits.
  Partial failures remain unavailable. Browser validates values, percentages,
  ordering and dates; charts/tables show Live provenance and UTC observation time.
  Refresh is manual; navigation/hidden-page/mode changes discard late responses.
  Demo fixtures now cover all six categories. No arbitrary PromQL or target URL
  is accepted from the browser. Readiness and series are local gateway features;
  production authentication remains the existing hosted acceptance gate.
- OPU-176: bounded safe answer formatting for bold, inline code, unordered lists
  and fenced code. Raw HTML/links stay text; code stays inert and never generates
  citations. Large/complex input has a plain-text fallback. Question/source labels
  stay escaped. Citations, routing/latency and partial failures remain visible.
- OPU-177 safety fix: account Demo payload preparation now rejects explicitly
  Live turns, preserving provenance instead of relabelling them. Browser Demo
  history already rejects Live. This is not Live persistence implementation.

## Verification

- Frontend full suite: **152 passed, zero failed/skipped**. Tests include actual
  loopback HTTP gateway routes with controlled upstream responses, fixed query
  restrictions, partial/invalid/oversized responses, stale/cancelled results,
  Live rendering and malicious Markdown. These are not operational backend runs.
- Syntax checks and 17-asset allowlisted build pass. Server operational module
  remains outside public assets. `git diff --check` passes.
- Browser tool inventory returns `apps: [], browsers: []`; no browser acceptance
  can be performed using connected UI surfaces.
- Docker CLI is installed, but the Docker engine pipe is absent. No real Docker
  service/backend acceptance was claimed or substituted with test responses.

## Open gates

| Issue | Why it cannot honestly be Done |
| --- | --- |
| OPU-105 | Previously deferred hosted identity/API/headers/rollback work; approved second email and protected backend origin are not established in this pass |
| OPU-175 | No connected browser surface; real viewport/keyboard/screen-reader/storage acceptance is unverified |
| OPU-177 | Live storage requires an explicit tenant-aware storage/retention decision, implementation and isolation acceptance; account Demo persistence is not Live persistence |
| OPU-63 | Final deployment review still requires actual Terraform/Helm/ArgoCD/telemetry/rollback and OPU-57/105/175 evidence; source/unit tests cannot sign it off |

OPU-106/107/176 Done refers to their completed local implementation. Their browser
and hosted checks remain in existing OPU-175/105; no duplicate acceptance tickets
were created. Original requirements are retained. Week 4 overall is incomplete.

All completion and remaining-work comments follow Prompt Engineer's prompt-design
guidance: specific delivered outcomes, verification, unknowns and next acceptance
steps. Jeffin's assigned issues/files are unchanged. No hosted configuration,
invitation, publication, deployment, provider query, commit or push occurred.
