# OPU-52: Cycle 3 review and integration documentation

Review: 2026-10-11 UTC, `joint` baseline `be782a3`.
Scope: review async/agent integrations, document integration points, and hand off
known limitations to Week 4. No runtime, provider, model, transport-default or
deployment changes are part of this task.

Deliverables: [architecture](../architecture/async-integration.md), corrected
README entry points and [contract notes](../orchestrator/CONTRACT.md).
Architecture/review files stay outside the ingested `docs/` corpus.

## Review scope and provenance

The sprint's scheduled dates do not establish the actual PR set. The repository
PRs and implementation follow-ups covering its scope were used:

| Change | Review basis | Current-branch conclusion |
| --- | --- | --- |
| [PR #1: agents/CI foundation](https://github.com/jeff13in/OpsBrain/pull/1) | PR metadata/diff inventory; current CI, manifests, agent boundaries and backend clients | Integrations exist; release/auth/deadline limitations remain |
| [PR #2: runbooks/configs](https://github.com/jeff13in/OpsBrain/pull/2) | Metadata/diff inventory; current tracked runbooks, schema and monitoring configuration | Fresh-clone dependencies tracked; not cluster deployment evidence |
| [PR #3: OPU-50 Kafka](https://github.com/jeff13in/OpsBrain/pull/3) | Kafka/graph/Monitoring diff plus current implementations/tests | Shared query handlers, per-process reply groups, correlation/deadlines and partial results implemented |
| `14fae10`, `2b0ef2e`, `c905c24`, `35f65a9`, `a1a806f` | Current Kafka, Infra/Code, contract/graph and OPU-62 follow-up | Bounded backend calls and typed failures; not forced whole-operation cancellation |
| `4fcd6db` / OPU-51 | Current fan-out/aggregation and historical pipeline record | Multi-topic Monitoring and live-pipeline fixes retained |
| OPU-80-83 migration; `be782a3` / OPU-60-61 | Current shared factory/query boundaries and test evidence | Separate Groq chat roles, Gemini embeddings, HTTP default and failure/serialization hardening retained |

This is source/evidence review, not a submitted GitHub approval or a claim that
all historical PR checks passed. Historical PR descriptions mention Gemini chat
and Kafka-default Compose; those are not the current runtime configuration.

## Integration conclusions

- Four-agent HTTP and opt-in Kafka converge on the same response contract.
- Failed parallel branches do not discard successful answers or citations.
- Correlation IDs plus expected-agent matching isolate simultaneous requests.
- Invalid wire records and malformed RAG/Monitoring output are not normal answers.
  Dependency 503s get one retry; timeouts do not.
- Router/synthesis failures retain deterministic fallbacks. Missing repository/
  cluster setup does not require further chat-model migration changes.
- Current Infra/Code live backend acceptance is incomplete; mocks and intentional
  absent-agent tests are not proof of real backend connectivity.

## Findings and Week 4 handoff

These are review recommendations, not new Linear issue assignments. P1 means
resolve before relying on the affected production/release behavior; P2 means
an explicit operating limitation requiring a follow-up decision.

| ID / priority | Evidence and impact | Suggested owner / next step |
| --- | --- | --- |
| R1 / P1 | [CI `on`](../../.github/workflows/ci-cd.yml): pushes only `main`/`jeffin-dev`; PRs only target `main`. `joint` pushes/PRs into `joint` do not trigger this workflow. Root-only README edits are outside the paths filter. | Shared/CI: add agreed collaboration-branch test/build gates and verify an actual run without broadening deployment triggers accidentally. |
| R2 / P1 | [CI](../../.github/workflows/ci-cd.yml) publishes GHCR SHA/`latest`; [manifests](../k8s/orchestrator.yaml) use placeholder ECR `latest`. Both `main` and `jeffin-dev` can overwrite GHCR `latest`. | Deployment / OPU-54-55: align registry/pull access and immutable promotion tags across manifests/Helm; test clean deployment. |
| R3 / P1 | [Code mutation routes](../agents/code/main.py) lack application auth; Compose publishes agent ports. Kafka clients lack configured TLS/SASL/ACLs. Correlation is not authorization. | Shared/deployment: protect ingress and rerun/dispatch, keep agent/broker access private, use least privilege before public exposure. |
| R4 / P1 | [Deploy step](../../.github/workflows/ci-cd.yml) uses `curl -s`, prints HTTP status and does not fail on HTTP errors. ArgoCD 401/403/500 can leave the shell step successful; no sync/health wait certifies deployment. | CI/GitOps / OPU-55: enforce HTTP failure and wait for sync/health; test rejected and successful paths. |
| R5 / P2 | [Worker `_run`](../shared/agent_bus.py) submits to a four-thread executor without a queue bound. Expired work is skipped only when execution starts; sustained load can grow memory/backlogs. | Async platform: add bounded submissions/backpressure; load-test overload without unexpected provider traffic. |
| R6 / P2 | [Consumer](../shared/kafka_client.py) auto-commits independently of handler completion; [worker](../shared/agent_bus.py) queues queries then publishes replies later. Crashes can lose committed work or replay uncommitted records. | Async platform: decide delivery/idempotency requirements; test crashes/restart. Do not claim exactly-once delivery. |
| R7 / P2 | [Worker/bus](../shared/agent_bus.py) retries initial connection but exits/closes on post-startup consumer failure. Pending calls release, but the listener does not restart itself; health is not complete readiness. | Async/deployment: reconnect or fail readiness/restart on listener loss; verify recovery. |
| R8 / P2 | [Graph](../orchestrator/graph.py) bounds caller waits, not synchronous work. [AWS client](../agents/infra/agent.py) permits two bounded attempts, potentially exceeding 30s; retries/sequential calls extend end-to-end time. | Agent/platform: choose whole-operation/ask budgets and bound resources while retaining model/API policies unless explicitly changed. |
| R9 / P2 | [Memory](../orchestrator/memory.py) is process-local; [manifest](../k8s/orchestrator.yaml) has two replicas. Follow-up context can disappear when requests move replicas. | Deployment / OPU-54: select shared storage or stickiness; test cross-replica conversations. |
| R10 / P2 | [Code client](../agents/code/agent.py) embeds upstream error bodies/URLs; [Infra](../agents/infra/agent.py) includes some exception text. API boundaries propagate these messages, unlike hardened RAG/Monitoring. | Agent owners: safe client messages/server-only diagnostics and redaction tests, preserving error classification. |

Real repository selection/token scope, AWS permissions, a Kubernetes connection
and metrics-server remain deferred by user choice. Terraform inspection needs
an installed CLI/existing state; it does not generate plans. Kubernetes Kafka
uses a different image reference from local Compose; availability and advertised
listeners must be checked in the target cluster, not assumed from local tests.
Provider quotas, demo-only metrics, keyword-based Monitoring and opt-in DB/broker
coverage in CI remain limitations, not migration failures.

## Recorded evidence: tested boundaries

These are checked-in historical records, not fresh OPU-52 live runs:

| Evidence | Recorded result | Boundary |
| --- | --- | --- |
| [OPU-51](OPU-51.md) | Historical full Kafka pipeline and integration fixes | Pre-Groq chat; missing Infra/Code credentials produced partial answers |
| [Provider/full run](integration-full-results.json) | 14 passed, 3 failed | Actual provider/HTTP services; unconfigured GitHub/cluster paths and partial aggregate |
| [HTTP](integration-http-results.json), [Kafka](integration-kafka-results.json) | 7/7 each | Live Groq/RAG/Monitoring, not full four-backend acceptance |
| [OPU-60](OPU-60.md), [results](opu60-live-results.json) | 181 regression tests; 6/6 broker checks | Real broker, synthetic agents, no provider calls |
| [OPU-61](OPU-61.md), [results](opu61-live-results.json) | 217 tests, no skips; 8/8 broker checks | Includes local pgvector rollback; real RAG/Monitoring handlers, injected backends, synthetic Code and absent Infra |
| [OPU-62](OPU-62.md) | Infra/Code failure/deadline verification | Does not provision/certify actual AWS/GitHub/Kubernetes backends |

## OPU-52 verification and closeout

Fresh checks on this baseline (documentation-only working changes):

| Check | Result |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest tests -q`, from `opsbrain/` | **216 passed, 1 skipped**, 43.17s; 219 upstream deprecation warnings |
| Ruff across agents/orchestrator/shared/scripts/tests | Passed |
| Local Markdown file-link targets in all six changed/new documents | **64 checked**, all exist; external URLs and heading anchors excluded |
| `git diff --check` | Passed; Git line-ending warnings only |
| Change scope | Markdown only; no runtime/config or ingested runbook changes |

The database test skipped because `RAG_TEST_DATABASE_URL` was not configured for
this offline run. Previously recorded 217/no-skip results included an explicit
database connection. No new live/backend acceptance is implied by this run.
No service restart/rebuild, external model call, ingestion, secret edit, cloud
operation, GitHub approval, commit or push was performed for this task.

Review/documentation deliverables are ready for shared review. OPU-51, the stated
full-pipeline dependency, remains **In Review**, so OPU-52 remains **In Review**
instead of implying full production acceptance. To close Cycle 3, reviewers must
accept the documented limited live coverage/deferred backends or finish the
missing backend checks, then close OPU-51 and approve this handoff. Week 4 findings
are recommendations here; unrelated issues were not modified.
