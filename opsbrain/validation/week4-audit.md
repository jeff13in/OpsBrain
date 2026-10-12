# Week 4 outstanding-work review — October 12, 2026

Reviewed all 14 open active OPU tickets and four open legacy TES tickets in
the Week 4 milestones against current source, full Linear descriptions and
dependency relations. The user requested straightforward fixes, not deployment
or blanket completion. All deployment/hosted acceptance gates remain open.

## Fixes completed locally

- **Observability review:** corrected local and Kubernetes latency rules to
  separate model-backed services: HTTP p95 thresholds RAG 30s, orchestrator 45s,
  others 2s; execution p95 RAG 45s, others 20s, sustained for 10 minutes. These
  are initial tuning profiles, not production SLOs.
- **Observability review:** added bounded `opsbrain_agent_failures_total`
  labels (`agent`, contract `error_code`) while preserving the existing execution
  counter. One final outcome is counted once, including after retry. Critical
  repeated-failure alerts select timeout/unavailable/invalid-response only;
  bad input and configuration/agent-error 500s are excluded from this critical
  rule. HTTP 5xx visibility remains through its existing warning rule.
The user subsequently excluded Jeffin-assigned tickets from this pass. The
latest OPU-53/54/55/58 edits and their associated Terraform, service manifests,
dashboard generation/CI and README changes were rolled back to the prior
committed baseline. Earlier completed work is preserved. Those four tickets
are restored to Backlog with their prior descriptions/dependencies/links.

## Every outstanding ticket

| Ticket(s) | Review result and work remaining |
| --- | --- |
| OPU-53 / TES-12 | Jeffin-owned active scope excluded; latest changes reverted, previous state restored |
| OPU-54 / TES-10 | Jeffin-owned active scope excluded; latest changes reverted, previous state restored |
| OPU-55 / TES-10 | Jeffin-owned active scope excluded; latest changes reverted, previous state restored |
| OPU-57 | Full deployed PDF acceptance and real telemetry still require deployment and Week 3 live backend setup/acceptance (OPU-100–103) |
| OPU-58 / TES-6 | Jeffin-owned active scope excluded; latest changes reverted, previous state restored |
| OPU-63 | Empty review ticket given explicit Week 4 review gates and dependencies; reviewer sign-off is still required |
| OPU-84 | Visual foundation/components verified by existing tests/build; responsive/browser/keyboard review remains |
| OPU-85 | Landing/navigation tests pass. Later Week 5 login/signup expands the older no-signup scope; do not remove that implemented work to match the historical description. Hosted/access/browser evidence remains |
| OPU-86 | Demo scenarios/provenance tested; real browser acceptance and hosted restrictions remain |
| OPU-87 | Chat/citations/escaping/failure cases pass; browser/keyboard acceptance remains |
| OPU-88 | Chart fixtures/refresh/provenance tests pass; browser acceptance remains; live snapshots are not historical charts |
| OPU-89 | Storage/expiry/corruption tests pass, but current expiry is creation +72h while Linear says last-message update +72h. Current docs/tests deliberately specify absolute retention. Reconcile that acceptance decision; behavior is preserved here |
| OPU-90 | Adapter/gateway/contract tests pass, including real local HTTP transport with a controlled backend; real OpsBrain services and protected hosted connectivity remain unverified |
| OPU-91 | Build, static server and credential-pattern checks pass; approved two-engineer identities, access to all asset/preview/API paths, hosted browser checks and deployment/rollback remain |
| TES-8 | Observability implementation and local configuration fixes verified; real deployed stack acceptance remains |

Canceled legacy TES-1–4 are historical proposals and were not reopened. Existing
Done OPU-56/64 are not recertified as production deployment evidence by this audit.

## Verification

| Check | Result |
| --- | --- |
| Full Python suite | **312 passed, 1 skipped**, 38 subtests passed; 26.33s |
| Frontend `npm test` | **120 passed**, including local HTTP tests on authorized loopback rerun |
| Frontend `npm run check` / `npm run build` | Passed; 14 allowlisted assets |
| Production/script/changed-test Ruff | Passed |
| Kubernetes YAML | Earlier 20-document check included now-reverted deployment edits; no retained image/readiness fix claim |
| Local + Kubernetes alert PromQL | **13 expressions parsed** |
| Generated dashboard ConfigMaps | Latest generated files/helper/CI gate removed with OPU-54 rollback |
| Terraform HCL | Latest edits reverted; previous configuration restored |
| `git diff --check` | Passed |
| Local Markdown targets in the changed entry points/runbook/audit | **31 checked**, all exist |
| Built public assets credential-pattern scan | **0 findings** |

The skipped Python test needs `RAG_TEST_DATABASE_URL`. YAML/HCL/PromQL parsing
is syntax validation, not Kubernetes server admission, Prometheus rule evaluation
or Terraform provider/plan validation. No Docker build, cluster apply, AWS plan/
apply, real backend call, browser visual audit, hosted deployment, PR approval,
commit or push was performed. Backend deployment/access gates remain open.


## Ownership boundary

Future work must skip tickets assigned to Jeffin unless the user explicitly
changes that instruction. Retained changes from this pass are observability
metrics/alerts, their tests/runbook, shared/unassigned review notes and dependency
links that do not modify Jeffin's tickets. No earlier Week 1–3 or already
completed Jeffin work was reverted.


## Assigned-to-Rifat follow-up

The [assigned-scope follow-up](week4-rifat.md) resolves OPU-89’s retention
mismatch and OPU-87/90’s missing routing/latency and stale-answer handling.
Frontend regression: 122 passed. Earlier retention observations above are
historical. Jeffin’s reverted work remains excluded; no deployment occurred.
