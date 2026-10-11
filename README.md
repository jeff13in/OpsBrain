# OpsBrain — Agentic DevOps Intelligence Platform

OpsBrain is an AI system that answers questions like *"why is the website slow?"*
by asking several specialist agents at once (runbooks, live metrics, AWS/Kubernetes,
GitHub) and merging their answers, so a DevOps engineer doesn't have to check
10 different tools by hand when something breaks.

All code lives in `opsbrain/`; run every command below from that folder unless
it says otherwise. The full operations guide is [`opsbrain/README.md`](opsbrain/README.md),
and the orchestrator/agent contract is [`opsbrain/orchestrator/CONTRACT.md`](opsbrain/orchestrator/CONTRACT.md).

Cycle 3 handoff: [async architecture](opsbrain/architecture/async-integration.md)
and [OPU-52 review / Week 4 limitations](opsbrain/validation/OPU-52.md).

### Branches

| Branch | What it is |
|---|---|
| `joint` | Shared development from `rifat-updated`, including OPU-60/61. CI does not yet run on pushes/PRs into this branch (OPU-52 finding R1). |
| `jeffin-dev` | Integration source branch; configured CI runs on matching pushes here |
| `rifat-updated` | Source for `joint`: merged Groq migration, observability, agent integrations and pipeline fixes |
| `main` | Stable branch, last updated from `jeffin-dev` via PR #1 (Sept 8), plus a title rename on Oct 2. Behind `jeffin-dev` |
| `Rifat` | Rifat's original work in the old root layout (`rag/`, `monitoring/`, `data/`). Fully merged into `jeffin-dev` (PR #2), so start new work from `jeffin-dev` instead |

---

## Architecture

```
User (curl / CLI / Slack later)
       │  POST /ask {question, session_id?}
       ▼
┌──────────────────────────────────────────────────────────┐
│ Orchestrator :8000   (LangGraph)                         │
│  route ──► call agents in parallel ──► synthesise answer │
│  Groq picks agents + rewrites follow-ups;                │
│  keyword routing if no key / LLM fails                   │
└────┬──────────────┬───────────────┬───────────────┬──────┘
     │ HTTP POST /query by default
     │ or Kafka (opt-in overlay, OPU-50):
     │ opsbrain.agent.<agent>.requests / opsbrain.agent.replies
     ▼              ▼               ▼               ▼
┌─────────┐   ┌───────────┐   ┌──────────┐   ┌───────────┐
│  RAG    │   │Monitoring │   │  Infra   │   │   Code    │
│  :8001  │   │  :8002    │   │  :8003   │   │   :8004   │
└────┬────┘   └─────┬─────┘   └────┬─────┘   └─────┬─────┘
 pgvector      Prometheus      AWS (EC2/EKS/     GitHub PRs,
 runbooks      Grafana         RDS), Kubernetes, commits, Actions,
 + Groq        Alertmanager    Terraform         deployments
```

### What works today

| Component | Status | What it does |
|---|---|---|
| **Orchestrator** | ✅ Working (OPU-42/43/50/51/80) | Routes each question to one or more agents with Groq, calls them in parallel over HTTP or Kafka, merges the answers, remembers the conversation per `session_id` |
| **RAG Agent** | ✅ Working (OPU-82) | Searches runbooks in pgvector (Gemini embeddings) and answers with Groq `gpt-oss-120b`, citing sources |
| **Monitoring Agent** | ✅ Working (`/query` added in OPU-50) | Prometheus queries, Grafana dashboards, Alertmanager alerts, pod health, scrape-target status; `/query` answers every topic a question mentions |
| **Infra Agent** | ✅ Working (OPU-48, OPU-62) | EC2/EKS/RDS state, Kubernetes pods/nodes/deployments/resource usage, Terraform plan, combined health summary |
| **Code Agent** | ✅ Working (OPU-49, OPU-62) | PRs and their CI status, commits, workflow runs, deployments; can rerun/trigger workflows via explicit endpoints only |
| **Kafka** | ✅ Wired in and run live (OPU-47/50/51) | Carries every orchestrator → agent request and reply. Live results: [`opsbrain/validation/OPU-51.md`](opsbrain/validation/OPU-51.md) |
| **CI/CD** | ✅ Lint + tests + image builds to GHCR | Tests now fail the build when they fail. AWS deploy stage is not live |

---

## How a question is answered

1. **Route.** With `LLM_API_KEY` set, Groq `gpt-oss-20b` picks the agents and rewrites
   follow-ups so they stand alone ("did it break them?" → "Did PR #42 break the
   api pods?"). Without a key, or if the model fails, is rate-limited (429) or takes
   over 10s, whole-word keyword matching
   picks agents (e.g. *alert, prometheus* → monitoring; *pod, eks, rds* → infra;
   *pr, commit, pipeline* → code). Nothing matched → RAG.
2. **Call agents in parallel.** Each agent gets `{question, request_id}` with its
   own timeout (RAG 60s, others 30s). A 503, or Kafka refusing the message, is
   retried once. An agent that never replies counts as a timeout.
3. **Merge.**
   - One agent answered → its answer, word for word.
   - Two or more answered → Groq Qwen 27B combines them (or labelled sections without a key, or after 20s).
   - Some agents failed → the answer says which ones were unavailable.
4. **Respond.** HTTP **200** if at least one agent answered (`status: ok` or
   `partial`), **502** if none did (`status: error`). The body has the same shape
   either way.

### Chat models (OPU-80)

Chat generation uses Groq's free tier, one model per step, through `shared/llm.py`
(any OpenAI-compatible endpoint works, including a local Ollama):

| Step | Default model | Env var |
|---|---|---|
| Routing | `openai/gpt-oss-20b` | `LLM_MODEL_ROUTER` |
| RAG answers | `openai/gpt-oss-120b` | `LLM_MODEL_ANSWER` |
| Merging answers | `qwen/qwen3.8-27b` | `LLM_MODEL_SYNTH` |

Set `LLM_API_KEY` (free at console.groq.com). `GOOGLE_API_KEY` is now only for the
Gemini embeddings the RAG agent uses.

### How messages travel: HTTP, or Kafka (OPU-50)

Compose uses HTTP by default. Kafka is opt-in:
`docker compose -f docker-compose.yml -f docker-compose.kafka.yml --profile full up --build -d`.
The k8s manifests set `AGENT_TRANSPORT=kafka`. With Kafka on:

- The orchestrator publishes a `KafkaAgentRequest` to `opsbrain.agent.<agent>.requests`
  and waits for the `KafkaAgentReply` with the same `correlation_id` on `opsbrain.agent.replies`.
- Each agent runs a background worker (`shared/agent_bus.py`) that answers by calling
  its own `/query`, so the status codes below are the same as over HTTP. The agents'
  HTTP APIs keep working too.
- Every orchestrator process reads all replies and keeps its own, so the 2 k8s replicas work.
- Agents skip requests the orchestrator has already given up on. Malformed messages are
  logged and dropped. Services keep retrying while the broker starts up.
- Without `AGENT_TRANSPORT=kafka`, the orchestrator calls agents over HTTP (`<NAME>_AGENT_URL`).

### How agents report failures (OPU-62)

Agents never return an error as a normal answer. `/query` returns:

| Status | Meaning | Orchestrator treats it as |
|---|---|---|
| 503 | Backend down, slow, throttled or rate-limited | `unavailable`, retried once |
| 404 / 400 | The PR/commit/workflow doesn't exist, or bad input | `bad_request`, not retried |
| 500 | Missing or wrong credentials, permissions or config | `agent_error`, not retried |

Backend calls have per-call limits: AWS 5s connect / 20s read / 2 attempts,
Kubernetes 20s per call, GitHub 10s per request. These do not guarantee the
whole operation finishes within the orchestrator's 30s caller budget;
synchronous work can continue after timeout. See the integration architecture.

---

## Quick start

### Prerequisites
- Docker + Docker Compose
- A Groq chat API key (`LLM_API_KEY`)
- A Google AI Studio API key (free: https://aistudio.google.com/apikey)
- Optional: AWS credentials / kubeconfig (Infra Agent), `GITHUB_TOKEN` + `GITHUB_REPO` (Code Agent)

A fresh clone has everything `docker-compose.yml` mounts: the runbooks (`docs/`),
`database/init.sql`, and the Alertmanager, Grafana and Prometheus-rules configs
are all tracked in git (merged in from Rifat's branch in PR #2).

### 1. Configure
```bash
cd opsbrain
cp .env.example .env
# set LLM_API_KEY (Groq), GOOGLE_API_KEY (embeddings) and POSTGRES_PASSWORD;
# optionally AWS_*, KUBECONFIG, GITHUB_TOKEN, GITHUB_REPO
```

### 2. Start everything
```bash
docker compose --profile full up --build -d
docker compose ps
```

| Service | Address |
|---|---|
| Orchestrator | http://localhost:8000 (Swagger UI at `/docs`) |
| RAG / Monitoring / Infra / Code agents | http://localhost:8001 / 8002 / 8003 / 8004 |
| Postgres (pgvector) | localhost:**5434** (5432/5433 are taken by native Postgres installs on the dev Mac) |
| Prometheus / Alertmanager / Grafana | http://localhost:9090 / 9093 / 3000 |
| Demo pod metrics | http://localhost:9100 |
| Kafka | localhost:9092 |

`docker compose --profile full down` stops everything; database and Kafka data
survive in volumes.

### 3. Load the runbooks
`opsbrain/docs/` is mounted into the RAG agent as `/app/data`:
```bash
curl -s -X POST http://localhost:8001/ingest \
  -H "Content-Type: application/json" -d '{"directory": "/app/data"}'
# → {"documents_processed": 2, "chunks_stored": ...}
```

### 4. Ask the orchestrator
```bash
curl -s -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "Are any alerts firing on the EKS pods?", "session_id": "me"}'
```

Response (shortened):
```json
{
  "status": "ok",
  "answer": "...",
  "sources": ["alertmanager:alerts", "kubernetes:pods"],
  "routing": {"agents": ["monitoring", "infra"], "method": "keyword", "reason": "monitoring: firing; infra: eks"},
  "results": [
    {"agent": "monitoring", "status": "ok", "answer": "...", "sources": ["alertmanager:alerts"]},
    {"agent": "infra", "status": "ok", "answer": "...", "sources": ["kubernetes:pods"]}
  ]
}
```
If an agent fails, `status` is `partial` and its entry in `results` carries the
error code. Send the next question with the same `session_id` to ask a follow-up.

---

## Talking to agents directly

### RAG Agent (:8001)
| Method | Path | Body |
|---|---|---|
| `POST` | `/ingest` | `{"directory": "/app/data"}` |
| `POST` | `/query` | `{"question": "...", "top_k": 4}` (question ≥ 5 chars, top_k 1–10) |

The response has `answer`, `sources`, `grounded`, `validation_errors` and
`retrieved_chunks`. `grounded` alone doesn't prove the answer came from the model;
the agent returns an extractive fallback when generated citations don't check out.

### Monitoring Agent (:8002)
| Method | Path | Description |
|---|---|---|
| `POST` | `/query` | Orchestrator entry point: answers every topic mentioned (alerts by default, pod health for pod/crash/restart, scrape targets for "down"/target); 503 only if every backend asked is unreachable |
| `POST` | `/metrics/query` | Instant or range PromQL (`query`, optional `start`/`end`/`step`) |
| `GET` | `/dashboards/{uid}` | Grafana dashboard metadata and panels |
| `POST` | `/dashboards/panel-query` | Query a Grafana datasource with PromQL |
| `GET` | `/alerts`, `/alerts/summary` | Alertmanager alerts / summary by state and severity |
| `GET` | `/pods/health?namespace=` | Pod phase, readiness, restarts (from kube-state-metrics) |

The local stack includes a demo exporter with one healthy pod (`demo/api-0`) and
one crash-looping pod (`demo/worker-0`) that fires `DemoPodRestarting`. Wait
~10s after startup, then:
```bash
curl -s "http://localhost:8002/pods/health?namespace=demo"
curl -s http://localhost:8002/alerts/summary
curl -s -X POST http://localhost:8002/metrics/query -H "Content-Type: application/json" -d '{"query": "up"}'
```
Expected: two demo pods (one healthy, one degraded), one active
`DemoPodRestarting` warning, and a non-zero `result_count`.

### Infra Agent (:8003)
`POST /query` plus typed endpoints: `/aws/instances`, `/aws/instances/summary`,
`/aws/eks`, `/aws/rds`, `/k8s/pods`, `/k8s/nodes`, `/k8s/deployments`,
`/k8s/usage`, `/terraform/plan`, `/health/summary`. Without AWS credentials or a
kubeconfig these return **500** with a message saying what's missing.

### Code Agent (:8004)
`POST /query` plus `/pulls`, `/pulls/{n}`, `/pulls/{n}/status`, `/commits`,
`/commits/{sha}`, `/actions/runs`, `/actions/summary`, `/deployments`,
`/deployments/{id}/status`. Workflows are rerun or triggered only through
`POST /actions/runs/{id}/rerun` and `POST /actions/workflows/{workflow}/dispatch`,
never from a free-text question. Needs `GITHUB_TOKEN` and `GITHUB_REPO=owner/repo`.

---

## Project structure

```text
OpsBrain/                      ← git repo root (github.com/jeff13in/OpsBrain)
├── .github/workflows/ci-cd.yml   lint → test → build/push images to GHCR → deploy (not live)
├── README.md                     this file
└── opsbrain/
    ├── orchestrator/
    │   ├── main.py           /ask and /health
    │   ├── graph.py          LangGraph: route → parallel call_agent → synthesise
    │   ├── router.py         agent registry (URLs, timeouts) + keyword routing
    │   ├── llm.py            routing and answer merging (Groq via shared/llm.py)
    │   ├── contract.py       error mapping and aggregation rules
    │   ├── memory.py         per-session conversation memory
    │   └── CONTRACT.md       the orchestrator ↔ agent contract
    ├── agents/
    │   ├── rag/              ingestion, retrieval, LangGraph RAG agent
    │   ├── monitoring/       Prometheus / Grafana / Alertmanager tools
    │   ├── infra/            AWS, Kubernetes, Terraform tools
    │   └── code/             GitHub PRs, commits, Actions, deployments
    ├── shared/               Pydantic models (incl. contract), config, Kafka client,
    │                         agent_bus.py (orchestrator ↔ agent request/reply over Kafka)
    ├── docs/                 runbooks the RAG agent ingests
    ├── database/init.sql     pgvector schema, applied on first Postgres start
    ├── infra/
    │   ├── prometheus/       scrape config + alert rules
    │   ├── alertmanager/     alert routing (local: no-op receiver)
    │   ├── grafana/          datasource + "OpsBrain Monitoring Overview" dashboard
    │   └── terraform/        AWS infrastructure (VPC, EKS, RDS, S3); not applied yet
    ├── k8s/                  Kubernetes manifests; not deployed yet
    ├── tests/                unit + integration tests (run offline)
    ├── scripts/validate_rag.py   live RAG check against Postgres + Gemini
    ├── validation/           OPU-40 (RAG) and OPU-51 (full Kafka pipeline) validation records
    └── docker-compose.yml
```

---

## Development


### Run tests and lint
From `opsbrain/` (tests use fakes and moto, so no Docker, AWS or API key needed):
```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/
.venv/bin/ruff check agents/ orchestrator/ shared/
```
CI runs the same two commands on every push to `main` or `jeffin-dev` (and on PRs
into `main`), and a failing test fails the build. It does not run on `joint`
pushes or PRs into `joint`. The latest recorded combined regression run was
217 passed with the opt-in database test configured; see
[`opsbrain/validation/OPU-61.md`](opsbrain/validation/OPU-61.md).

### Live RAG check
Needs `GOOGLE_API_KEY` for embeddings and `LLM_API_KEY` for Groq chat in the
running stack. It reingests the runbooks
and checks storage, retrieval, and a grounded answer:
```bash
DATABASE_URL="postgresql://opsbrain:<POSTGRES_PASSWORD>@localhost:5434/opsbrain" \
PYTHONPATH=agents .venv/bin/python -m scripts.validate_rag --directory docs --api-directory /app/data
```
`--directory` is where this script reads the runbooks (on your machine);
`--api-directory` is where the RAG container sees the same files.

### Add a runbook
Put a `.md` or `.txt` file in `opsbrain/docs/` and run the ingest command again.

---

## Known gaps

CI, deployment, authorization and delivery findings are recorded in the
[OPU-52 handoff](opsbrain/validation/OPU-52.md). Implemented integration does
not imply full four-backend or production deployment acceptance.

- **Infra/Code real-backend acceptance is deferred on this setup**; current
  pipeline evidence includes missing configuration and partial-result paths,
  not proof of successful AWS/Kubernetes/GitHub integration on this branch.
- **Questions under 5 characters fail** ("hi" → RAG's 422 → HTTP 502); see `CONTRACT.md` gap 3.
- **Provider quotas are account/model-specific**; consult the provider dashboard
  instead of assuming fixed daily free-tier capacity. Fallbacks preserve service
  behavior but do not increase provider quota.
- **Alert thresholds need tuning** (review on OPU-64): the latency alerts fire at 2s/10s, but RAG
  and `/ask` normally take 5–28s.
- **Monitoring's `/query` picks its answer by keyword** (alerts, pods or scrape targets);
  it doesn't build PromQL from the question.
- **Conversation memory is per process.** `k8s/orchestrator.yaml` runs 2 replicas,
  so follow-ups can lose context there until memory moves to a shared store (OPU-54).
- **Nothing is deployed to AWS yet.** Terraform, Helm and ArgoCD are OPU-53/54/55.

## Roadmap

- [x] **Stage 1:** RAG agent (runbook search, Q&A; now on Groq, OPU-82)
- [x] **Stage 2:** Orchestrator, all four agents, Kafka fan-out (OPU-50), live pipeline run (OPU-51)
- [ ] **Stage 3:** Terraform deploy to AWS EKS, ArgoCD GitOps
- [~] **Stage 4:** Prometheus metrics, Grafana dashboards, Loki logs, alerts ✅ (OPU-56); Slack integration, CLI tool still to do
