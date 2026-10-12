# Week 1–3 sprint audit

Reviewed October 12, 2026, on the local `joint` checkout. Linear requirements,
issue descriptions, milestone assignments, dependency relationships and relevant
review comments were compared with the current source and checked-in evidence.
Code/documentation fixes from this audit are local and uncommitted.

## Scope and ticket coverage

The active plan is **OpsBrain September Delivery Plan** (OpusBrain / OPU).
There are no team cycles; the weeks are project milestones. Ticket descriptions
establish their intended week, even where the milestone was wrong.

| Week | Tickets reviewed | Implementation/evidence | Acceptance remaining |
| --- | --- | --- | --- |
| 1 — Foundation and RAG | OPU-35–40 | Repo/env/schema, Compose, five Dockerfiles, chunking/idempotent source replacement, pgvector retrieval, LangGraph RAG, API validation and citation fallback; `OPU-40.md`, ingestion/RAG/database tests | Fresh Docker/database/provider acceptance was not rerun; historical evidence is retained |
| 2 — Monitoring, Orchestration and CI | OPU-41–46, OPU-59 | PromQL/Grafana/alerts/pod tools; shared contract; parallel graph, failure aggregation, per-session memory; CI tests/build/GHCR; graph/monitoring/contract tests and recorded HTTP/Kafka smoke | Completed in the subsequent [Week 2 closeout](week2-closure.md): OPU-44 and OPU-46 Done; all seven active Week 2 tickets Done |
| 3 — Async, Infra and Code | OPU-47–52, OPU-60–62 | Kafka utilities/models/workers/bus, correlations/deadlines, typed failures, AWS/Kubernetes and GitHub tools; bus/failure/resilience tests; `OPU-51.md`, `OPU-60.md`, `OPU-61.md`, `OPU-62.md`, async architecture | OPU-51 stays In Review: full real AWS/Kubernetes/GitHub success coverage is missing. OPU-52 returned to In Review because its OPU-51 prerequisite remains unresolved |

The older **OpsBrain September Sprint** project (TEst / TES) was also inspected.
Its Week 1–3 backlog overlaps the active plan:

| Older ticket | Active coverage |
| --- | --- |
| TES-30 / project setup | OPU-35 |
| TES-26 / Docker and Postgres | OPU-36–37 |
| TES-28 / ingestion | OPU-38 |
| TES-24 / RAG retrieval | OPU-39 |
| TES-22 / Monitoring | OPU-41 |
| TES-20 / Orchestrator | OPU-42–44 |
| TES-14 / CI/CD | OPU-45 (GHCR supersedes ECR) |
| TES-16 / Kafka | OPU-47, OPU-50 |
| TES-18 / Infra and Code | OPU-48–49, OPU-62 |

Canceled TES tasks describe earlier proposals (GPT-4o, synchronous gather,
PyGithub, cluster apply) and are not treated as current implementation criteria.
They were not reopened or counted as a second set of deliverables. Project dates
and legacy ticket states are preserved; this audit does not replan the calendar.

## Defects fixed

1. **Plural keywords missed agents when model routing was unavailable.**
   `Are alerts active?` and `List commits` defaulted to RAG because whole-word
   matching only recognized singular terms. Matching now accepts an optional
   plural `s`, including `pull requests`, while retaining word boundaries and
   registry order. A regression checks all four agents and substring avoidance.
2. **Invalid short input appeared as an upstream outage.** `/ask` accepted `hi`
   and whitespace, then RAG rejected the request and aggregation returned 502.
   `/ask` now trims the question and validates 5–2000 characters before routing,
   returning 422 without calling the graph or provider. This deliberately aligns
   public validation with RAG's existing minimum. Endpoint regressions cover
   short/blank/padded/oversized questions and valid trimmed input.
3. **Code Agent falsely reported unsuccessful checks as successful.** Completed
   checks with `cancelled`, `timed_out`, `action_required`, `startup_failure` or
   `stale` conclusions now yield overall `failure`. Missing or unfamiliar
   completed conclusions yield `unknown`; successful/neutral/skipped checks
   retain existing success behavior. The summary now also incorporates legacy commit-status contexts, so passing check runs cannot hide a failed or pending external CI status. Incomplete check-run pages yield `unknown`. Private-repository tokens require Commit statuses read permission; this adds one bounded GitHub GET to the PR lookup. Endpoint tests cover each conclusion, mixed/legacy-only/empty status sets, incomplete pages and access denial. GitHub’s combined-state semantics follow the [official API documentation](https://docs.github.com/en/rest/commits/statuses#get-the-combined-status-for-a-specific-reference).
4. **Setup instructions were stale.** Corrected the removed `opsbrain-overview`
   dashboard to the tracked service-health/agent-activity UIDs; all five services
   already expose `/metrics`. Updated public question validation, variable
   ingestion counts and demo alert startup timing in the README entry points.

## Linear corrections

- Restored OPU-36 to Week 1; OPU-42–44 to Week 2; OPU-50–51 to Week 3,
  matching the original requirements rather than later accidental assignments.
- Added the described but missing `blockedBy` links across OPU-36–51. Existing
  dependencies are retained. In particular, OPU-46 now exposes the pending
  OPU-44 review and OPU-51 explicitly depends on OPU-50.
- Renamed OPU-45's title to GHCR, matching its existing registry-migration update.
- Updated OPU-44, OPU-46, OPU-49 and OPU-52 descriptions with evidence and review boundaries.
  Completed implementation does not establish complete sprint acceptance.

## Fresh verification

| Check | Result |
| --- | --- |
| Python 3.12.9; `python -m pytest tests -q` | **289 passed, 1 skipped**, 38 subtests passed; 21.75s |
| `ruff check agents orchestrator shared scripts` plus the three changed test modules | Passed |
| `git diff --check` | Passed |
| Local Markdown links across README, operations guide, contract and both audit records | **49 checked**, all targets exist; external URLs and heading anchors excluded |
| Linear readback | Corrected week assignments, review states and all added dependency links confirmed |

The skipped test requires `RAG_TEST_DATABASE_URL`; it is not a failed test.
The full suite uses controlled backend/provider responses, including in-memory
Kafka tests. No fresh Docker builds, real broker, database, provider, selected
GitHub repository, AWS or Kubernetes run occurred. Recorded live results are
historical and explicitly narrower than all-four-backend success acceptance.

Expanded Ruff checking of **all** test modules also found eight pre-existing
lint findings in Week 5's `test_account_flows.py` and `test_account_security.py`.
Those are outside this audit's Week 1–3 changes and outside CI's configured lint
scope. The production sources and modified test modules pass.

## Remaining operational work

- Configure the chosen GitHub repository/token and reachable AWS/Kubernetes
  backends, then rerun OPU-51 against all four successful agents. Accept the
  dependency and shared closeout review before closing OPU-52.
- RAG re-ingestion replaces present, nonempty sources; deleted/emptied files are
  not a corpus synchronization mechanism. The README already documents tuning
  variables that are not consumed. Large-corpus indexing remains a separate
  dimension/index design; existing vectors are not re-embedded by this audit.
- CI configuration exists, but this session does not certify remote checks,
  image publication or branch protection. PR status is a diagnostic summary,
  not a certificate that branch protection permits merging.
- Kafka still needs bounded queues, runtime consumer recovery and explicit
  crash/delivery/idempotency semantics. Backend calls can outlive caller budgets.
- Replica memory, backend error redaction, agent mutation authorization,
  broker access controls and deployment manifests remain the documented
  operating/release follow-ups in `OPU-52.md`. ArgoCD's HTTP failure handling has
  since been fixed in the workflow; sync/health/rollback acceptance remains open.

These limits are preserved as work to verify, not converted into passing
acceptance by unit tests or Done states. No commit, push or deployment was made.


## Subsequent Week 2 completion

The user requested completion of all outstanding Week 2 work. The follow-up
[closeout](week2-closure.md) adds five tests through the real orchestrator and
RAG/Monitoring apps and records source review, **294 passed / 1 skipped** and
relevant lint success. OPU-44 and OPU-46 are now Done. Legacy TES-24, TES-20
and TES-22 are also closed against the same verified implementation and linked
to active OPU coverage. Earlier In Review states above are audit history;
Week 3/backend and Week 4 operational limits remain open.
