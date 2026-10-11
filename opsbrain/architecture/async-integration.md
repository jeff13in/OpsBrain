# Async platform and agent integrations

OPU-52 baseline: `joint` at `be782a3`, reviewed 2026-10-11 UTC.
This describes implemented behavior, not production deployment acceptance.
See the [contract](../orchestrator/CONTRACT.md), [operations guide](../README.md)
and [Cycle 3 review / Week 4 handoff](../validation/OPU-52.md).
Architecture lives outside `docs/`, which Compose mounts for RAG ingestion;
these notes must not silently change the runbook corpus.

## End-to-end flow

```text
POST /ask {question, session_id?}
  -> load process-local history
  -> route / rewrite follow-up (Groq or keyword fallback)
  -> parallel LangGraph branches for selected agents
       HTTP default: POST <agent>/query
       Kafka opt-in: request topic -> worker -> same /query ASGI handler
                                    reply topic -> correlated waiting branch
  -> normalize results, aggregate status and successful sources
  -> synthesize answers or deterministic labeled fallback
  -> AskResponse; remember non-error turn
```

Routing/results use registry order `rag`, `monitoring`, `infra`, `code`, regardless
of completion order. A failed branch does not cancel successful peers. `/ask`
returns 200 for `ok` or `partial`, and 502 when no agent succeeded (`error`).
Its response includes `request_id`, `session_id`, `question`, `status`, `answer`,
`sources`, `routing` and `results`, including per-agent latency/error information.

## Transport configuration

[Base Compose](../docker-compose.yml) defaults `AGENT_TRANSPORT` to `http`.
[The Kafka override](../docker-compose.kafka.yml) enables workers and the bus.
From `opsbrain/`:

```powershell
# Existing HTTP flow
docker compose --profile full up --build -d
# Explicit Kafka flow; not required just to read/review documentation
docker compose -f docker-compose.yml -f docker-compose.kafka.yml --profile full up --build -d
```

Set transport consistently for the orchestrator and all intended agents.
Kafka mode does not automatically fail over to HTTP when Kafka fails. Direct
agent HTTP APIs remain available. `KAFKA_BOOTSTRAP_SERVERS` defaults to
`kafka:9092` inside Docker; host clients need the published host address.
The [Kubernetes manifests](../k8s/orchestrator.yaml) explicitly select Kafka;
they have deployment gaps and are not proof of a working cluster.

## Topics, envelopes and correlation

| Topic | Producer -> consumer | Envelope / consumer group |
| --- | --- | --- |
| `opsbrain.agent.rag.requests` | Orchestrator -> RAG | `KafkaAgentRequest`; `rag-agent` |
| `opsbrain.agent.monitoring.requests` | Orchestrator -> Monitoring | `KafkaAgentRequest`; `monitoring-agent` |
| `opsbrain.agent.infra.requests` | Orchestrator -> Infra | `KafkaAgentRequest`; `infra-agent` |
| `opsbrain.agent.code.requests` | Orchestrator -> Code | `KafkaAgentRequest`; `code-agent` |
| `opsbrain.agent.replies` | All workers -> every orchestrator process | `KafkaAgentReply`; unique `orchestrator-<random>` group per process |

Source: [models](../shared/models.py), [wire client](../shared/kafka_client.py),
[worker/bus](../shared/agent_bus.py), [graph](../orchestrator/graph.py).
Requests contain `correlation_id`, `agent`, `query: {question, request_id}`,
`reply_topic` and an absolute Unix-time `deadline`. Each attempt gets a new
correlation ID; the request ID identifies the parent `/ask`, not a single reply.
Replies carry correlation ID, agent, HTTP-equivalent `status_code` and `body`.
The reply listener waits for partition assignment before publishing. Each process
sees all replies but resolves only its own pending ID and expected agent.
Duplicate, late, unknown and wrong-agent replies are ignored.

Wire messages must be UTF-8 JSON objects with finite numbers. Schema validation
rejects invalid identifiers, agent names, deadlines and HTTP statuses. Malformed
records are dropped; handler failures do not terminate consumption. Worker
exceptions/unserializable output become safe 500 envelopes. These checks are
schema/correlation validation, not authentication of broker publishers.

Workers use four execution threads by default and invoke their own `/query`
through an in-process ASGI client without re-entering application lifespan.
They skip expired requests before execution. Synchronize host clocks because
cross-service expiration uses absolute time.

## Agent integration points

| Agent / port | `/query` dependency path | Configuration / acceptance needs |
| --- | --- | --- |
| RAG / 8001 | Gemini embeddings -> pgvector retrieval -> Groq answer -> citation validation | `DATABASE_URL`, `GOOGLE_API_KEY`, `LLM_API_KEY`; ingest runbooks separately |
| Monitoring / 8002 | Keyword-selected alert summary, pod health and/or scrape targets | Reachable Prometheus/Alertmanager; Grafana for direct dashboard endpoints; demo pod exporter is not Kubernetes |
| Infra / 8003 | AWS EC2/EKS/RDS, Kubernetes resources/usage, Terraform state/plan-file inspection | AWS read permissions; reachable cluster/kubeconfig; metrics-server for usage; Terraform executable/state |
| Code / 8004 | GitHub PRs, commits, Actions/check runs and deployments | Explicit `GITHUB_REPO=owner/repo`; appropriate token scope for private data/actions |

Each `agents/<agent>/main.py` attaches the worker. HTTP/Kafka share validation and
response/error boundaries. RAG retains grounding/validation/retrieval metadata;
Monitoring retains per-topic data and can answer partially when another topic
fails. RAG/Monitoring reject empty/nonserializable success output with safe 500s;
dependency outages return safe 503s. Infra/Code propagate typed backend statuses.

`/query` is read-oriented. Code rerun/dispatch uses separate explicit POST
endpoints, never natural-language routing. Those routes still require auth before
external exposure. `/terraform/plan` uses `terraform show -json`, not plan/apply
or a fresh drift check. Base Compose has no host kubeconfig mount; the optional
[Kubernetes override](../docker-compose.kubernetes.yml) uses `KUBECONFIG_HOST`.
Backend selection and credentials remain operator-owned.

## Failures, retries and deadlines

| Outcome | Classification | Retry |
| --- | --- | --- |
| Valid 2xx answer | `ok` | None |
| Invalid successful body | `invalid_response` | None |
| 4xx input/resource error | `bad_request` | None |
| 503, refused HTTP connection, Kafka unavailable/publish failure | `unavailable` | One retry |
| Other 5xx | `agent_error` | None |
| Deadline elapsed | `timeout` | None, despite retryable metadata |

Per-attempt budgets: RAG 60s, others 30s. HTTP has a wall-clock deadline; Kafka
readiness, publication and reply waiting share the attempt budget. An absent
Kafka worker times out; a refused HTTP connection is unavailable. Cancellation/
shutdown cleans pending futures; reply-consumer loss releases pending calls.

Caller deadlines do not forcibly stop synchronous work already running in a
thread. AWS has per-attempt connect/read limits and up to two attempts;
Kubernetes/GitHub have per-call limits. Retries or sequential backend calls can
continue after the caller gives up. Late replies cannot change a finished answer.
Two transport attempts plus routing/synthesis may exceed one agent's budget.
There is no single whole-`/ask` deadline or bounded worker submission queue.

## Models and memory: preserved migration flow

[Shared chat factory](../shared/llm.py): `LLM_BASE_URL` + `LLM_API_KEY`, with
router `openai/gpt-oss-20b`, RAG answer `openai/gpt-oss-120b` and synthesis
`qwen/qwen3.8-27b`, independently overridable using `LLM_MODEL_<ROLE>`.
Router/synthesis have 10s/20s wall-clock deadlines; RAG chat has a 45s request
timeout. SDK retries are disabled. Provider failures use existing keyword,
retrieved-snippet or labeled-answer fallbacks; synthesis preserves sources and
unavailable-agent reporting. Gemini remains the embedding provider only:
`models/gemini-embedding-001`, 3072 dimensions, unchanged by transport.

[Session memory](../orchestrator/memory.py) retains six question/answer pairs,
expires after one idle hour and caps 1000 sessions per process. Kafka reply
groups isolate correlation across replicas but do not share memory. Shared
storage/sticky routing is needed for reliable cross-replica follow-ups.

## Operations and delivery limits

`/health` is not complete backend readiness; verify actual read-only dependency
queries and a grounded `/ask`. Metrics/logging/alerts are documented in the
[observability guide](../docs/observability.md). Initial Kafka connections retry
with backoff; a consumer that exits after startup currently needs a service
restart, not an automatic application reconnect loop.

Local Kafka is a single development broker without production TLS/ACLs.
Auto-committed offsets are not tied to handler completion/reply publication:
crashes can lose or duplicate delivery. No exactly-once promise, durable pending
request store, idempotency layer or dead-letter workflow exists.

Offline tests exercise serialized in-memory transport/injected backends.
[OPU-60](../validation/OPU-60.md) and [OPU-61](../validation/OPU-61.md) separately
record real-broker resilience. The [review](../validation/OPU-52.md) distinguishes
those from live-provider checks and deferred GitHub/AWS/Kubernetes acceptance.
