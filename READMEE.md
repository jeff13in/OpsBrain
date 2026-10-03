# OpsBrain — Agentic DevOps Intelligence Platform

OpsBrain is an AI system that answers questions like *"why is the website slow?"*
by asking several specialist agents at once (runbooks, live metrics, AWS/Kubernetes,
GitHub) and merging their answers, so a DevOps engineer doesn't have to check
10 different tools by hand when something breaks.

This file describes the `jeffin-dev` branch. All code lives in `opsbrain/`; run
every command below from that folder unless it says otherwise. The full
operations guide is [`opsbrain/README.md`](opsbrain/README.md), and the
orchestrator/agent contract is [`opsbrain/orchestrator/CONTRACT.md`](opsbrain/orchestrator/CONTRACT.md).

---

## Architecture

```
User (curl / CLI / Slack later)
       │  POST /ask {question, session_id?}
       ▼
┌──────────────────────────────────────────────────────────┐
│ Orchestrator :8000   (LangGraph)                         │
│  route ──► call agents in parallel ──► synthesise answer │
│  Gemini picks agents + rewrites follow-ups;              │
│  keyword routing if no key / LLM fails                   │
└────┬──────────────┬───────────────┬───────────────┬──────┘
     │ POST /query  │               │               │      (HTTP today; Kafka is OPU-50)
     ▼              ▼               ▼               ▼
┌─────────┐   ┌───────────┐   ┌──────────┐   ┌───────────┐
│  RAG    │   │Monitoring │   │  Infra   │   │   Code    │
│  :8001  │   │  :8002    │   │  :8003   │   │   :8004   │
└────┬────┘   └─────┬─────┘   └────┬─────┘   └─────┬─────┘
 pgvector      Prometheus      AWS (EC2/EKS/     GitHub PRs,
 runbooks      Grafana         RDS), Kubernetes, commits, Actions,
 + Gemini      Alertmanager    Terraform         deployments
```

### What works today

| Component | Status | What it does |
|---|---|---|
| **Orchestrator** | ✅ Built (OPU-42/43), not yet run against live agents | Routes each question to one or more agents, calls them in parallel, merges the answers, remembers the conversation per `session_id` |
| **RAG Agent** | ✅ Working | Searches runbooks in pgvector and answers with Gemini, citing sources |
| **Monitoring Agent** | ✅ Tools work · ⚠️ no `/query` yet | Prometheus queries, Grafana dashboards, Alertmanager alerts, pod health. The orchestrator can't send it questions until it has `/query` |
| **Infra Agent** | ✅ Working (OPU-48, OPU-62) | EC2/EKS/RDS state, Kubernetes pods/nodes/deployments/resource usage, Terraform plan, combined health summary |
| **Code Agent** | ✅ Working (OPU-49, OPU-62) | PRs and their CI status, commits, workflow runs, deployments; can rerun/trigger workflows via explicit endpoints only |
| **Kafka** | ✅ Producer/consumer library (OPU-47) | Not wired into the agents yet (OPU-50) |
| **CI/CD** | ✅ Lint + tests + image builds to GHCR | Tests now fail the build when they fail. AWS deploy stage is not live |

---

## How a question is answered

1. **Route.** With `GOOGLE_API_KEY` set, Gemini picks the agents and rewrites
   follow-ups so they stand alone ("did it break them?" → "Did PR #42 break the
   api pods?"). Without a key, or if Gemini fails, whole-word keyword matching
   picks agents (e.g. *alert, prometheus* → monitoring; *pod, eks, rds* → infra;
   *pr, commit, pipeline* → code). Nothing matched → RAG.
2. **Call agents in parallel.** Each agent gets `POST /query {question, request_id}`
   with its own timeout (RAG 60s, others 30s). An agent that is unreachable or
   returns 503 is retried once.
3. **Merge.**
   - One agent answered → its answer, word for word.
   - Two or more answered → Gemini combines them (or labelled sections without a key).
   - Some agents failed → the answer says which ones were unavailable.
4. **Respond.** HTTP **200** if at least one agent answered (`status: ok` or
   `partial`), **502** if none did (`status: error`). The body has the same shape
   either way.

### How agents report failures (OPU-62)

Agents never return an error as a normal answer. `/query` returns:

| Status | Meaning | Orchestrator treats it as |
|---|---|---|
| 503 | Backend down, slow, throttled or rate-limited | `unavailable`, retried once |
| 404 / 400 | The PR/commit/workflow doesn't exist, or bad input | `bad_request`, not retried |
| 500 | Missing or wrong credentials, permissions or config | `agent_error`, not retried |

Backend calls are time-limited so an agent always answers within the
orchestrator's budget: AWS 5s connect / 20s read / 2 attempts, Kubernetes 20s
per call, GitHub 10s per request.

---

## Quick start

### Prerequisites
- Docker + Docker Compose
- A Google AI Studio API key (free: https://aistudio.google.com/apikey)
- Optional: AWS credentials / kubeconfig (Infra Agent), `GITHUB_TOKEN` + `GITHUB_REPO` (Code Agent)

> The runbooks (`docs/`), `database/init.sql` and the Alertmanager, Grafana and
> Prometheus-rules configs come from Rifat's branch and are tracked in git as of
> `rifat-updated`, so a fresh clone has everything `docker-compose.yml` mounts.

### 1. Configure
```bash
cd opsbrain
cp .env.example .env
# set GOOGLE_API_KEY and POSTGRES_PASSWORD; optionally AWS_*, KUBECONFIG, GITHUB_TOKEN, GITHUB_REPO
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
  "status": "partial",
  "answer": "...",
  "sources": ["kubernetes:pods"],
  "routing": {"agents": ["monitoring", "infra"], "method": "keyword", "reason": "monitoring: firing; infra: eks"},
  "results": [
    {"agent": "monitoring", "status": "error", "error": {"code": "bad_request", "retryable": false}},
    {"agent": "infra", "status": "ok", "answer": "...", "sources": ["kubernetes:pods"]}
  ]
}
```
(Monitoring shows `bad_request` until it gets a `/query` endpoint.) Send the
next question with the same `session_id` to ask a follow-up.

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
Devops/                        ← git repo root
├── .github/workflows/ci-cd.yml   lint → test → build/push images to GHCR → deploy (not live)
├── READMEE.md                    this file
└── opsbrain/
    ├── orchestrator/
    │   ├── main.py           /ask and /health
    │   ├── graph.py          LangGraph: route → parallel call_agent → synthesise
    │   ├── router.py         agent registry (URLs, timeouts) + keyword routing
    │   ├── llm.py            Gemini routing and answer merging
    │   ├── contract.py       error mapping and aggregation rules
    │   ├── memory.py         per-session conversation memory
    │   └── CONTRACT.md       the orchestrator ↔ agent contract
    ├── agents/
    │   ├── rag/              ingestion, retrieval, LangGraph RAG agent
    │   ├── monitoring/       Prometheus / Grafana / Alertmanager tools
    │   ├── infra/            AWS, Kubernetes, Terraform tools
    │   └── code/             GitHub PRs, commits, Actions, deployments
    ├── shared/               Pydantic models (incl. contract), config, Kafka client
    ├── tests/                unit + integration tests (run offline)
    ├── scripts/validate_rag.py   live RAG check against Postgres + Gemini
    ├── infra/terraform/      AWS infrastructure (VPC, EKS, RDS, S3); not applied yet
    ├── k8s/                  Kubernetes manifests; not deployed yet
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
CI runs the same two commands, and a failing test now fails the build.

### Live RAG check
Needs the stack running with a real `GOOGLE_API_KEY`. It reingests the runbooks
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

- **Monitoring has no `/query` endpoint**, so orchestrator questions routed there fail (OPU-44).
- **Agents talk over HTTP only.** Kafka fan-out is OPU-50; the full live pipeline run is OPU-51.
- **The orchestrator hasn't been run against live agents or a real Gemini key yet.**
- **Conversation memory is per process.** `k8s/orchestrator.yaml` runs 2 replicas,
  so follow-ups can lose context there until memory moves to a shared store (OPU-54).
- **`k8s/orchestrator.yaml` still sets `OPENAI_API_KEY`**; the orchestrator now uses `GOOGLE_API_KEY` (OPU-54).
- **Nothing is deployed to AWS yet.** Terraform, Helm and ArgoCD are OPU-53/54/55.

## Roadmap

- [x] **Stage 1:** RAG agent (runbook search, Q&A via Gemini)
- [~] **Stage 2:** Orchestrator ✅ and all four agents ✅; Monitoring `/query` and Kafka fan-out still to do
- [ ] **Stage 3:** Terraform deploy to AWS EKS, ArgoCD GitOps
- [ ] **Stage 4:** Prometheus/Grafana dashboards for the agents, Slack integration, CLI tool

.