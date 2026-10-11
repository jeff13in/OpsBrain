# OpsBrain — Agentic DevOps Intelligence Platform (Setup & Operations Guide)

OpsBrain is a set of small FastAPI "agent" services — RAG (runbooks), Monitoring
(Prometheus/Grafana/Alertmanager), Infra (AWS/Kubernetes/Terraform), and Code
(GitHub) — meant to sit behind a single Orchestrator that answers DevOps
questions like *"why is the website slow?"* by pulling context from all four.

This guide documents the **current branch as it actually behaves**, verified
against the source code, `docker-compose.yml`, and `.env.example` — not
assumptions carried over from another branch or an earlier design doc. Where
something is implemented but unfinished (or wired up but pointing at nothing
real yet), it's called out explicitly rather than implied to work.

All commands are Windows PowerShell, copy-paste-ready from the `opsbrain/`
directory.

---

## Table of contents

1. [Setup and service management](#1-setup-and-service-management)
2. [RAG Agent — port 8001](#2-rag-agent--port-8001)
3. [Monitoring Agent — port 8002](#3-monitoring-agent--port-8002)
4. [Infra Agent — port 8003](#4-infra-agent--port-8003)
5. [Code Agent — port 8004](#5-code-agent--port-8004)
6. [Orchestrator — port 8000](#6-orchestrator--port-8000)
7. [End-to-end demonstration](#7-end-to-end-demonstration)
8. [Troubleshooting and development](#8-troubleshooting-and-development)
9. [Architecture, project structure, and roadmap](#9-architecture-project-structure-and-roadmap)

---

> Production observability (Prometheus metrics, Grafana dashboards, Loki logs,
> alerts, Kubernetes/Helm deployment, and runbooks) is documented in
> [`docs/observability.md`](docs/observability.md).

## 1. Setup and service management

### Groq chat setup (OPU-80)

Chat generation uses `shared/llm.py` and LangChain `ChatOpenAI` against Groq's
OpenAI-compatible Chat Completions endpoint. Gemini remains the embedding
provider. Add these settings to your existing `.env` without replacing secrets:

```dotenv
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=
LLM_MODEL_ROUTER=openai/gpt-oss-20b
LLM_MODEL_ANSWER=openai/gpt-oss-120b
LLM_MODEL_SYNTH=qwen/qwen3.8-27b
```

Create a key at <https://console.groq.com/keys> and fill in `LLM_API_KEY` locally.
The synthesis identifier is verified against the
[Groq model catalog](https://console.groq.com/docs/models) on October 10, 2026;
Qwen is a preview model and may change or be removed. Check your account's
`/models` listing before rollout. `GOOGLE_API_KEY` is still needed for ingestion
and query embeddings. `GOOGLE_CHAT_MODEL` is no longer used by chat code.

| Role | Default model | Deadline | Output token cap |
|---|---|---|---|
| Router | `openai/gpt-oss-20b` | 10 seconds (wall clock) | 1024 |
| RAG answer | `openai/gpt-oss-120b` | 45 seconds (HTTP timeout) | 2048 |
| Synthesis | `qwen/qwen3.8-27b` | 20 seconds (wall clock) | 1536 |

All clients disable automatic retries. A router HTTP 429 immediately selects
keyword routing without backoff. Routing timeout/invalid JSON also use keywords.
Synthesis timeout/429/provider failures retain every available agent answer in
plain labeled sections with unavailable-agent information. RAG chat failures
use existing retrieved snippets and citation validation. `grounded: true`
describes retrieved evidence, not proof that a provider generated the prose.
The output caps limit daily token use without changing retrieved evidence or
embedding dimensions; reasoning tokens can consume the cap on reasoning models.

Groq limits include tokens/minute and tokens/day as well as requests/day. The
current published GPT-OSS free allowance is 200K tokens/day per model; at about
3,300 total tokens per answer this is roughly 60 answers/day, not 1,000. Check
[your account's active limits](https://console.groq.com/settings/limits), monitor
usage, and tune caps based on observed answers. Short caps may produce empty
or incomplete answers; the existing fallbacks remain available.

For optional Ollama, run/pull your chosen local model and set all three model
variables to its installed name:

```dotenv
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL_ROUTER=your-installed-model
LLM_MODEL_ANSWER=your-installed-model
LLM_MODEL_SYNTH=your-installed-model
```

Ollama requires no actual key, but the client needs a nonempty placeholder.
Docker Desktop containers use `http://host.docker.internal:11434/v1`; Linux
containers need a reachable host/service address. The factory is tested for
this configuration; local model quality, speed, and provider behavior require
live testing. Direct Python runs read process environment variables; Compose
reads `.env` and forwards them to the containers.

Rebuild the two affected images:

```powershell
docker compose --profile full up --build -d orchestrator rag-agent
```

For Kubernetes apply `k8s/chat-config.yaml`, manage `llm-api-key` and
`google-api-key` in the existing `opsbrain-secrets` through your secret manager,
and roll out rebuilt images. Override the ConfigMap for local endpoints or
alternate models; no plaintext credentials belong in it. Existing database
configuration remains a separate deployment prerequisite.

Run offline tests and live validation from `opsbrain/`:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python -m ruff check agents orchestrator shared scripts
# Live: export LLM_* and GOOGLE_API_KEY into the process securely first.
$env:PYTHONPATH = ".;agents"
$env:RAG_AGENT_URL = "http://localhost:8001"
$env:MONITORING_AGENT_URL = "http://localhost:8002"
$env:INFRA_AGENT_URL = "http://localhost:8003"
$env:CODE_AGENT_URL = "http://localhost:8004"
python -m scripts.validate_chat
# Existing validation additionally needs DATABASE_URL for host port 5434.
python -m scripts.validate_rag --directory docs --api-directory /app/data
python -m scripts.validate_rag --directory docs --api-directory /app/data --question "How do I handle exhausted database connections?" --expected-source runbook-db-connections.md
```

`validate_chat` writes `validation/opu80-live-results.json`; exit 2 means no
credentials and no live checks executed. Its reconstructed question set covers
both runbooks and all agent types. No original OPU-51 question set exists in this
checkout or the issue's comments. The async implementation here uses HTTP;
Kafka is now available through the opt-in override and Monitoring has `/query`;
the Infra/Code agents still need backend configuration. See [validation/OPU-80.md](validation/OPU-80.md) for executed
checks and remaining acceptance requirements.

### Integrated agent transports (OPU-50 follow-up)

Monitoring now implements `/query` for alerts, pod health and scrape targets,
using its existing Prometheus/Alertmanager backends. Groq routing/answer/synthesis,
Gemini embeddings and all observability endpoints remain unchanged.

HTTP remains the default (`AGENT_TRANSPORT=http`). To opt into Kafka request/reply
for every agent, apply the transport override; it starts/waits for the broker:

```powershell
docker compose -f docker-compose.yml -f docker-compose.kafka.yml --profile full up --build -d orchestrator rag-agent monitoring-agent infra-agent code-agent
```

Kafka workers call the same validated `/query` handlers; correlation IDs,
deadlines, partial failures and citations use the existing response contract.
Kafka is a transport only: provider-level retries remain disabled and router/
synthesis models and deadlines do not change. Broker outages are reported as
unavailable, not silently hidden by HTTP fallback. This local broker is unsecured;
keep it private and add authentication/TLS before any external deployment.

For an already configured non-production Kubernetes deployment, Kafka can also
be opted into explicitly (these commands restart the selected deployments):

```powershell
kubectl -n opsbrain set env deployment/orchestrator deployment/rag-agent deployment/monitoring-agent deployment/infra-agent deployment/code-agent AGENT_TRANSPORT=kafka KAFKA_BOOTSTRAP_SERVERS=kafka:9092
```

Set `AGENT_TRANSPORT=http` on those deployments to return to HTTP. Use images
built from this branch so Groq model configuration and metrics are retained;
do not replace the agent manifests with the older Gemini-based branch versions.
The bundled dev/staging broker explicitly enables automatic request/reply topic
creation. Production brokers should use managed topic provisioning and access
controls instead. No Kubernetes commands are needed for local HTTP usage.

To return to HTTP, ensure `.env` has `AGENT_TRANSPORT=http` (or leave it unset),
and recreate the agents without the override:

```powershell
docker compose --profile full up -d orchestrator rag-agent monitoring-agent infra-agent code-agent
```

The Code Agent still needs `GITHUB_REPO=owner/repo` (and a local `GITHUB_TOKEN`
for private access). Kubernetes still needs a real cluster; for containers use
the optional `docker-compose.kubernetes.yml` override with `KUBECONFIG_HOST`
pointing to a self-contained kubeconfig. Its API server must be reachable from
Docker; a host `localhost` address usually is not. Do not put credentials in Git.

### General prerequisites

- **Docker Desktop** running, with Compose v2 (`docker compose`, not the old
  `docker-compose`).
- A **Google AI Studio API key** for RAG embeddings
  (<https://aistudio.google.com/apikey>) and a **Groq API key** for chat
  (<https://console.groq.com/keys>), or a reachable local Ollama chat endpoint.
- Everything else (AWS credentials, a Kubernetes cluster, Terraform, a GitHub
  token) is **optional** and only needed for specific Infra/Code Agent
  features — covered in their sections below.

### Working directory

Every command in this guide assumes you're in the `opsbrain/` folder:

```powershell
Set-Location "C:\Users\rifat\OneDrive\Documents\GitHub\devops\opsbrain"
```

Adjust the path to wherever you cloned the repo.

### Create `.env` without overwriting existing configuration

```powershell
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env — now edit it and fill in GOOGLE_API_KEY and POSTGRES_PASSWORD."
} else {
    Write-Host ".env already exists — not overwritten. Diff it against .env.example if you want to see what's new:"
    # PowerShell has no built-in `diff`; Compare-Object works line-by-line:
    Compare-Object (Get-Content .env) (Get-Content .env.example)
}
```

`.env` is git-ignored — it never gets committed. `.env.example` is the
template checked into the repo; keep real secrets only in `.env`.

### Required vs. optional configuration, per agent

Values below are **placeholders** — never paste real secrets into a doc,
chat, or ticket.

| Agent | Required | Optional (feature-gated) |
|---|---|---|
| **RAG** (8001) | `GOOGLE_API_KEY` for embeddings; `POSTGRES_PASSWORD` for Postgres | `LLM_API_KEY` enables generated answers; otherwise retrieved snippets. `LLM_BASE_URL`, `LLM_MODEL_ANSWER`, `GOOGLE_EMBEDDING_MODEL` configure providers. |
| **Orchestrator** (8000) | none to start | `LLM_API_KEY` enables routing/synthesis; `LLM_BASE_URL`, `LLM_MODEL_ROUTER`, `LLM_MODEL_SYNTH` select providers/models. |
| **Monitoring** (8002) | none — works with defaults against the local Prometheus/Alertmanager/Grafana containers | `GRAFANA_API_TOKEN=<token>` — only needed if you disable Grafana's anonymous access; the default Compose setup enables anonymous Admin access, so this can stay blank |
| **Infra** (8003) | none to start the container | `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` — for `/aws/*`<br>`KUBECONFIG` — for `/k8s/*` (see the real limitation in [§4](#4-infra-agent--port-8003) before setting this)<br>Terraform CLI is **not installed** in this container at all — `/terraform/plan` cannot work regardless of env vars, see §4 |
| **Code** (8004) | none to start the container | `GITHUB_REPO=owner/repo` — required for every endpoint except `/health`<br>`GITHUB_TOKEN=<token>` — optional; without it you get unauthenticated GitHub API access (60 requests/hour, public repos only) |

### Starting the stack

The **Compose profile is called `full`** — nothing starts without it:

```powershell
docker compose --profile full up --build -d
```

- `--profile full` — every service in `docker-compose.yml` is tagged
  `profiles: [full]`; omitting this flag starts nothing.
- `--build` — rebuilds images from their Dockerfiles first (needed the first
  time, and any time agent code changes — see [§8](#8-troubleshooting-and-development)).
- `-d` — detached (background). Drop it the first time if you want to watch
  startup logs live.

Verify everything started:

```powershell
docker compose ps
```

Expect `postgres` and `prometheus` to show `(healthy)` — they have explicit
Compose healthchecks. The other 9 services show `running`/`Up` with no
healthcheck defined, which does **not** mean their application logic is
verified working — only that the container process is alive. Confirm each
agent is actually responding with the `/health` checks in
[§7](#7-end-to-end-demonstration).

### Starting individual services (with dependencies)

Compose resolves `depends_on` automatically — starting `rag-agent` alone
still brings up `postgres` first:

```powershell
docker compose --profile full up --build -d rag-agent
docker compose --profile full up --build -d monitoring-agent   # pulls in prometheus, alertmanager, pod-metrics, grafana
docker compose --profile full up --build -d infra-agent        # no dependencies
docker compose --profile full up --build -d code-agent         # no dependencies
docker compose --profile full up --build -d orchestrator       # no dependencies (calls rag-agent by hostname at request time, not startup)
```

### Status, logs, restart

```powershell
# One-line status of everything
docker compose ps

# Follow logs for one service (Ctrl+C to stop following)
docker compose logs -f rag-agent

# Last 100 lines, no follow
docker compose logs --tail 100 infra-agent

# Restart a service without rebuilding (fast — use after an env var change in .env)
docker compose restart code-agent
```

### Rebuilding / recreating after code or environment changes

- **Changed a `.py` file** in an agent → the image must be rebuilt (Docker
  bakes the source into the image at build time, it isn't volume-mounted for
  live-reload):
  ```powershell
  docker compose --profile full up --build -d rag-agent
  ```
- **Changed a variable in `.env`** → a plain `docker compose restart` does
  **not** pick up new `.env` values for most setups; recreate the container
  instead:
  ```powershell
  docker compose --profile full up -d --force-recreate infra-agent
  ```
- **Changed `docker-compose.yml` itself** (e.g. added a volume mount) →
  same: `up -d --force-recreate` (or `up -d`, which recreates automatically
  when Compose detects the service definition changed).

### Shutdown

**Normal shutdown** — stops and removes containers, but keeps your data
(Postgres volume, Kafka volume, Prometheus/Grafana volumes are untouched):

```powershell
docker compose --profile full down
```

Next `up` picks up right where you left off — no need to re-ingest docs or
recreate dashboards.

**Full reset, including data** — only do this if you actually want to lose
ingested runbooks, Grafana settings, and Prometheus's local metric history:

```powershell
docker compose --profile full down -v
```

`-v` deletes the named volumes (`postgres_data`, `kafka_data`,
`prometheus_data`, `grafana_data`). There is no confirmation prompt — this is
irreversible.

### Service reference table

| Service | Host port | Container port | Browser URL | Health check | API docs (Swagger) |
|---|---|---|---|---|---|
| postgres | **5434** | 5432 | — (no HTTP) | `docker compose exec postgres pg_isready -U opsbrain` | — |
| rag-agent | 8001 | 8001 | http://localhost:8001 | http://localhost:8001/health | http://localhost:8001/docs |
| orchestrator | 8000 | 8000 | http://localhost:8000 | http://localhost:8000/health | http://localhost:8000/docs |
| monitoring-agent | 8002 | 8002 | http://localhost:8002 | http://localhost:8002/health | http://localhost:8002/docs |
| infra-agent | 8003 | 8003 | http://localhost:8003 | http://localhost:8003/health | http://localhost:8003/docs |
| code-agent | 8004 | 8004 | http://localhost:8004 | http://localhost:8004/health | http://localhost:8004/docs |
| prometheus | 9090 | 9090 | http://localhost:9090 | http://localhost:9090/-/ready | — |
| alertmanager | 9093 | 9093 | http://localhost:9093 | — | — |
| grafana | 3000 | 3000 | http://localhost:3000 | — | — |
| pod-metrics (fake exporter) | 9100 | 9100 | http://localhost:9100/metrics | — | — |
| kafka | 9092 | 9092 | — (no HTTP) | — | — |

**Postgres is on host port 5434, not the usual 5432** — this Compose file
deliberately remaps it because this machine may already run Postgres
natively on 5432/5433. Inside the Docker network, other containers still
reach it as `postgres:5432` (the container port, not the remapped host
port) — that's why `DATABASE_URL` in Compose says `@postgres:5432/opsbrain`,
not `@postgres:5434/opsbrain`.

Visiting `http://localhost:8001` (or any agent's bare root) shows
`{"detail":"Not Found"}` — normal. FastAPI only responds on the paths it
defines; use `/health` or `/docs`.

---

## 2. RAG Agent — port 8001

The RAG agent uses Groq chat through the shared model factory and unchanged
Google Gemini embeddings through `langchain_google_genai`.

- **Chat model:** `openai/gpt-oss-120b` (env `LLM_MODEL_ANSWER`)
- **Embedding model:** `gemini-embedding-001`, 3072 dimensions (env
  `GOOGLE_EMBEDDING_MODEL`) — the Postgres table (`database/init.sql`) is
  hard-coded to `VECTOR(3072)` to match; changing the embedding model to one
  with a different dimension count would break ingestion without also
  changing the schema.

### Effective configuration (verified against `agents/rag/retriever.py`)

| Env var | Default | Set in Compose? | Notes |
|---|---|---|---|
| `GOOGLE_API_KEY` | *(required, no default)* | yes | |
| `GOOGLE_EMBEDDING_MODEL` | `models/gemini-embedding-001` | yes | |
| `LLM_MODEL_ANSWER` | `openai/gpt-oss-120b` | yes | Chat model |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | yes | Chat Completions endpoint |
| `LLM_API_KEY` | blank | yes | Blank enables extractive chat fallback |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/opsbrain` | yes, overridden to the real container DSN | |
| `PGVECTOR_TABLE` | `document_chunks` | **no** | not currently in `.env.example` or Compose — set it as a container env var if you need a different table name |
| `RAG_DEFAULT_TOP_K` | `4` | **no** | **not** the same variable as `.env.example`'s `RAG_TOP_K` — that one currently has no effect (see note below) |
| `RAG_MIN_SCORE` | `0.2` | **no** | retrieved chunks below this cosine-similarity score are dropped |
| `RAG_MAX_CONTEXT_CHARS` | `8000` | **no** | context sent to the LLM is truncated at this length |

**Documentation-vs-code mismatch worth knowing:** `.env.example` currently
lists `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, and `RAG_TOP_K`. None of these
three are read by any code path in this branch —
`agents/rag/ingestor.py`'s chunking always uses its Python defaults
(`chunk_size=1200`, `chunk_overlap=200`), and the retriever reads
`RAG_DEFAULT_TOP_K`, not `RAG_TOP_K`. Setting those three in `.env` today
does nothing. If you want to change chunking or top-k behavior, use the
variables in the table above instead (added as container-level env vars,
since Compose doesn't currently pass them through).

### Runbooks: `docs/` → `/app/data`

Compose mounts the host's `opsbrain/docs/` directory into the container at
`/app/data`, read-only:
```yaml
volumes:
  - ./docs:/app/data:ro
```
Drop any `.md` or `.txt` file into `opsbrain\docs\` and re-run `/ingest` — no
rebuild needed, since it's a live volume mount, not baked into the image.

```powershell
New-Item -ItemType Directory -Force -Path .\docs | Out-Null
"# New runbook`n`nContent here." | Out-File -Encoding utf8 .\docs\my-new-runbook.md
```

### `POST /ingest`

```powershell
$body = @{ directory = "/app/data" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8001/ingest -Method Post -ContentType "application/json" -Body $body
```

- `directory` defaults to `/app/data` if omitted — that's the **container
  path**, not a host path. Point it elsewhere only if you've mounted
  something else there.
- **Response fields:** `documents_processed` (int), `chunks_stored` (int).
- Re-running `/ingest` on the same directory is idempotent — existing chunks
  for each source file are deleted and replaced in the same transaction, not
  duplicated.
- **Failure modes:** `404` if the directory doesn't exist inside the
  container; `400` if the path isn't a directory or contains no non-empty
  `.md`/`.txt` files; `503` if `GOOGLE_API_KEY` is unset or the embedding
  library isn't installed; `500` for anything unexpected.

### `POST /query`

```powershell
$body = @{ question = "What should I do when CPU usage is high?"; top_k = 4 } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8001/query -Method Post -ContentType "application/json" -Body $body
```

- `question` — 5 to 2000 characters (shorter is rejected with `400`).
- `top_k` — 1 to 10, default 4.
- **Response fields:**
  - `answer` (string) — either real LLM-generated prose, or an extractive
    fallback (`"Based on the retrieved runbooks, here's the best grounded
    answer to: ..."` followed by raw chunk text) if the LLM path wasn't
    available or its answer failed citation validation.
  - `sources` (list of strings) — filenames of the chunks actually used.
  - `grounded` (bool) — `true` only if there were no validation errors *and*
    at least one chunk was retrieved.
  - `validation_errors` (list of strings) — e.g. "weak lexical overlap with
    the question", "no relevant context retrieved".
  - `retrieved_chunks` (int).
- **Failure modes:** `400` if the question is too short or malformed; `503`
  if the LLM/embedding backend can't be reached or `GOOGLE_API_KEY` is
  missing; `500` for unexpected errors.
- **Provider limits:** each `/query` embeds through Google and answers through
  Groq (when configured). Their quotas are independent. Chat 429/timeouts use
  retrieved snippets; embedding failures still prevent retrieval.

### Tests and validation that actually exist on this branch

Only these — nothing else is implemented or wired into CI:

```powershell
pip install -r requirements-dev.txt
pytest tests\test_rag_agent.py tests\test_ingestor.py -v
```
Both are unit tests against mocked dependencies — no real network or
database calls, no `GOOGLE_API_KEY` needed.

```powershell
pytest tests\test_database.py -v
```
Skips itself unless `RAG_TEST_DATABASE_URL` is set to a real Postgres
connection string — it's an opt-in regression test that creates a temporary
schema, runs `database/init.sql` twice (checking it's safe to re-run), and
rolls everything back. Does not touch your real `document_chunks` data.

```powershell
$env:PYTHONPATH = "agents"
python -m scripts.validate_rag --base-url http://localhost:8001 --directory .\docs --api-directory /app/data
```
This is a **live integration script**, not a unit test — it actually calls
the running RAG API, ingests twice, checks the database directly via
`psycopg`, and asks a real question. It requires: the stack running, a
configured `GOOGLE_API_KEY` for embeddings, `LLM_API_KEY` for Groq chat, and
network access to both APIs. Note the two different `--directory`
flags: `--directory` is the path *this script* reads locally to compute
expected chunk counts (point it at the host `docs\` folder), while
`--api-directory` is the path *the RAG container* reads from (`/app/data`,
since that's where the volume is mounted inside the container) — they must
resolve to the same actual files, just via different paths.

---

## 3. Monitoring Agent — port 8002

Talks to three backends: **Prometheus** (metrics), **Grafana** (dashboards),
**Alertmanager** (alerts) — all three run locally via Compose, all using
their **Docker service names** internally
(`http://prometheus:9090`, `http://grafana:3000`, `http://alertmanager:9093`).
From your host (PowerShell), you always call the monitoring-agent itself at
`localhost:8002`, which proxies to those internal hostnames — you generally
don't need to hit Prometheus/Grafana directly, though their own UIs are
reachable at `localhost:9090` and `localhost:3000` for manual poking around.

### `GET /health`

```powershell
Invoke-RestMethod http://localhost:8002/health
```
Returns `{"status": "ok", "services": {"prometheus": "...", "grafana": "...", "alertmanager": "..."}}`
— this only reports configured URLs, it does not verify those backends are
actually reachable.

### Prometheus queries — `POST /metrics/query`

```powershell
# Instant query
$body = @{ query = "up" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8002/metrics/query -Method Post -ContentType "application/json" -Body $body

# Range query
$body = @{ query = "up"; start = "2026-09-09T00:00:00Z"; end = "2026-09-09T01:00:00Z"; step = "60s" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8002/metrics/query -Method Post -ContentType "application/json" -Body $body
```
Response: `{"query", "result_type", "result_count", "result": [...]}` — the
`result` array is Prometheus's own raw result format, passed through mostly
as-is.

**What `up` will actually show you right now:** per
`infra/prometheus/prometheus.yml`, every agent (orchestrator, rag, monitoring,
infra, code) is configured as a Prometheus scrape target, but **none of them
implement a `/metrics` endpoint yet** — that's explicit unfinished work, not
a bug. Those 5 targets will show as `up == 0` (down). Only `prometheus`
itself (self-scrape) and `demo-kube-state-metrics` (the fake `pod-metrics`
exporter) will show as genuinely up.

### Scrape targets (Prometheus's own UI, not the agent)

```powershell
Start-Process "http://localhost:9090/targets"
```
Useful to see the same "5 agents down, 2 up" picture directly, and to check
"Last Scrape" timestamps.

### Demo pod metrics

```powershell
Invoke-RestMethod http://localhost:9100/metrics
```
This is the raw Prometheus exposition text from the **fake** exporter
(`agents/monitoring/demo_metrics.py`) — two hard-coded pods, `demo/api-0`
and `demo/worker-0`, in namespace `demo`. This is the *only* data source
behind `/pods/health` below — there is no real Kubernetes cluster involved
anywhere in the Monitoring Agent.

### `GET /alerts` and `GET /alerts/summary`

```powershell
Invoke-RestMethod http://localhost:8002/alerts
Invoke-RestMethod "http://localhost:8002/alerts?active_only=true"
Invoke-RestMethod http://localhost:8002/alerts/summary
```
`/alerts` → `{"count", "alerts": [{"alertname","severity","namespace","pod","state","summary","starts_at","ends_at"}]}`.
`/alerts/summary` → `{"total","active","suppressed","severity_breakdown","state_breakdown","top_alerts"}`.

The one alert rule wired up is `DemoPodRestarting`
(`infra/prometheus/rules/demo-alerts.yml`) — it fires when the fake
exporter's demo pod restart count exceeds a threshold. **Both Prometheus's
scrape interval and its rule evaluation interval are 15 seconds**
(`infra/prometheus/prometheus.yml`), so after the exporter's underlying data
changes, expect **up to ~30 seconds** before the rule evaluates and
Alertmanager reflects a new state — a request immediately after a change may
show stale results.

### Grafana dashboards

```powershell
Invoke-RestMethod http://localhost:8002/dashboards/opsbrain-overview
```
`opsbrain-overview` is the **verified real UID** — confirmed directly from
`infra/grafana/dashboards/opsbrain-overview.json` (`"uid": "opsbrain-overview"`).
That dashboard currently has exactly one panel ("Scrape Target Availability",
the `up` metric — same caveat as above, most targets will show down).

```powershell
$body = @{ datasource_uid = "prometheus"; expr = "up"; from_minutes_ago = 15 } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8002/dashboards/panel-query -Method Post -ContentType "application/json" -Body $body
```
`prometheus` is the **verified real datasource UID** — from
`infra/grafana/provisioning/datasources/prometheus.yml` (`uid: prometheus`).

You can also just open Grafana directly — anonymous Admin access is enabled
in this Compose setup, no login needed:
```powershell
Start-Process "http://localhost:3000"
```

### GET vs. POST — what's browser-navigable

`/health`, `/alerts`, `/alerts/summary`, `/pods/health`, and
`/dashboards/{uid}` are `GET` — paste the URL straight into a browser.
`/metrics/query` and `/dashboards/panel-query` are `POST` with a JSON body —
a browser can't drive these directly; use the PowerShell examples above (or
`/docs`'s Swagger UI, which can send POST bodies interactively).

### `GET /pods/health`

```powershell
Invoke-RestMethod http://localhost:8002/pods/health
Invoke-RestMethod "http://localhost:8002/pods/health?namespace=demo"
```
Reiterating: this reflects the **fake demo exporter's data only**, not a
real cluster. `{"namespace","total_pods","status_breakdown","pods":[...]}`.

---

## 4. Infra Agent — port 8003

Three independently-degrading capabilities: AWS (boto3), Kubernetes
(kubernetes client), Terraform (subprocess calling the `terraform` CLI).
**Read the limitations at the end of this section before assuming any of
this works out of the box** — the container starts and answers requests
regardless, but most capabilities need setup this repo doesn't currently do
for you.

### `GET /health`

```powershell
Invoke-RestMethod http://localhost:8003/health
```
Returns `{"status": "ok", "capabilities": {"aws": true/false, "kubernetes": true/false, "terraform": true/false}}`.

**This does not mean what it looks like it means** — see Limitation 1 below.

### `POST /query`

```powershell
$body = @{ question = "what instances are running?" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8003/query -Method Post -ContentType "application/json" -Body $body
```
Keyword routing (`agents/infra/agent.py::ask()`), checked in this order:
`"health"`/`"summary"`/`"overall"` → aggregate health summary;
`"deployment"` → Kubernetes deployment status; `"usage"`/`"resource"`/
`"cpu"`/`"memory"` → node resource usage; `"node"` → Kubernetes nodes;
`"pod"`/`"kubernetes"`/`"k8s"` → pod health; `"terraform"`/`"plan"` →
Terraform plan summary; `"eks"` → EKS clusters; `"rds"`/`"database"` → RDS
instances; anything else → defaults to an AWS EC2 summary. See Limitation 6
for what happens on failure. Note the order matters: a question containing
both "health" and "eks" (e.g. "is eks healthy") routes to the aggregate
health summary, not the EKS-specific endpoint — use `/aws/eks` directly if
you want just that.

### `GET /aws/eks`

```powershell
Invoke-RestMethod http://localhost:8003/aws/eks
```
`{"region","count","clusters":[{"name","status"}]}`. Needs `eks:ListClusters`
and `eks:DescribeCluster` permissions on top of the EC2 ones above.

### `GET /aws/rds`

```powershell
Invoke-RestMethod http://localhost:8003/aws/rds
```
`{"region","count","status_breakdown","instances":[{"identifier","status","engine","instance_class"}]}`.
Needs `rds:DescribeDBInstances`.

### `GET /k8s/deployments`

```powershell
Invoke-RestMethod http://localhost:8003/k8s/deployments
Invoke-RestMethod "http://localhost:8003/k8s/deployments?namespace=default"
```
`{"namespace","total_deployments","status_breakdown","deployments":[{"namespace","name","desired","ready","available","updated"}]}`.
A deployment counts as `"healthy"` in the breakdown only when `ready ==
desired`; anything else (including `desired: 0`) counts as `"degraded"`.

### `GET /k8s/usage`

```powershell
Invoke-RestMethod http://localhost:8003/k8s/usage
```
`{"total_nodes","nodes":[{"name","cpu","memory"}]}`. **Requires
`metrics-server` to be installed in the target cluster** — this reads
`metrics.k8s.io/v1beta1`, which is a separate add-on, not part of the core
Kubernetes API. Without it, this returns `503` with a message saying so
explicitly, not a silent empty result.

### `GET /health/summary`

```powershell
Invoke-RestMethod http://localhost:8003/health/summary
```
`{"overall": "healthy"|"degraded", "checks": {"ec2": {"ok","data"|"error"}, "eks": {...}, "rds": {...}, "nodes": {...}, "pods": {...}, "deployments": {...}}}`.
Runs all six checks independently — one backend being unreachable (e.g. no
AWS credentials) flips `overall` to `"degraded"` and that check's entry to
`{"ok": false, "error": "..."}`, but does **not** stop the other five from
running and returning real data. This is the one endpoint on this agent
that always returns `200`, even when every single backend fails — read
`overall` and each check's `ok` field, don't rely on the HTTP status code
here.

### `GET /aws/instances`

```powershell
Invoke-RestMethod http://localhost:8003/aws/instances
Invoke-RestMethod "http://localhost:8003/aws/instances?state=running"
```
`{"region","count","instances":[{"instance_id","name","state","instance_type","availability_zone","private_ip","public_ip"}]}`.
`state` filters by AWS's own instance-state values (`running`, `stopped`,
`terminated`, etc.).

### `GET /aws/instances/summary`

```powershell
Invoke-RestMethod http://localhost:8003/aws/instances/summary
```
`{"region","total","state_breakdown"}`.

### `GET /k8s/pods`

```powershell
Invoke-RestMethod http://localhost:8003/k8s/pods
Invoke-RestMethod "http://localhost:8003/k8s/pods?namespace=default"
```
`{"namespace","total_pods","status_breakdown","pods":[{"namespace","pod","phase","ready","restarts","node"}]}`.
This talks **directly to the Kubernetes API** — it is a completely separate
data path from the Monitoring Agent's Prometheus-based `/pods/health`
(§3), and from the fake `pod-metrics` demo exporter (Limitation 5).

### `GET /k8s/nodes`

```powershell
Invoke-RestMethod http://localhost:8003/k8s/nodes
```
`{"total_nodes","nodes":[{"name","ready","capacity"}]}`.

### `GET /terraform/plan`

```powershell
Invoke-RestMethod http://localhost:8003/terraform/plan
Invoke-RestMethod "http://localhost:8003/terraform/plan?plan_file=tfplan.out"
```
`{"terraform_dir","resource_change_count","action_breakdown"}`. See
Limitations 3, 4, and 5 — this endpoint cannot currently succeed as shipped.

### AWS credentials, region, permissions

Set in `.env`: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
(defaults to `us-east-1` if unset). The credentials need, at minimum,
`ec2:DescribeInstances` for `/aws/instances*`, `eks:ListClusters` +
`eks:DescribeCluster` for `/aws/eks`, and `rds:DescribeDBInstances` for
`/aws/rds` — all read-only. Then recreate the container so it picks up the
new env vars:
```powershell
docker compose --profile full up -d --force-recreate infra-agent
```

### Kubernetes configuration and access

Set `KUBECONFIG` in `.env` to a kubeconfig file path, **but read Limitation
2 below first** — as shipped, this does not work without an additional
Compose change you'd have to make yourself.

### Terraform prerequisites

None currently possible in this container — see Limitation 3. If you want
to actually use this endpoint, you'd need to add a Terraform install step to
`agents/infra/Dockerfile` yourself; that's not done in this branch.

### Documented limitations (verified against source, not assumed)

1. **`/health`'s capability flags mean "the library is importable" / "the
   binary is on PATH" — not "this backend is reachable and authenticated."**
   `capabilities.aws` and `capabilities.kubernetes` are `true` in this
   container simply because `boto3`/`kubernetes` are installed
   (`agents/infra/Dockerfile`) — they stay `true` even with zero AWS
   credentials configured or no kubeconfig at all. A structured endpoint
   call is the only way to find out if a backend actually works; expect
   `503` with a descriptive error if it doesn't.

2. **Compose passes `KUBECONFIG` as an environment variable but does not
   mount a kubeconfig file into the container.** Setting `KUBECONFIG=C:\Users\...\config`
   in `.env` sets that *path string* inside the Linux container — but no
   file exists at that path inside the container, because Windows host
   paths aren't automatically visible to containers. Without a volume mount,
   the Kubernetes client will fail to load any config. **This is a real
   prerequisite you'd have to add yourself**, e.g. by adding a bind mount
   under `infra-agent.volumes` in `docker-compose.yml` such as
   `- ${KUBECONFIG}:/root/.kube/config:ro` and setting
   `KUBECONFIG=/root/.kube/config` for the container — this is not already
   wired up in this branch.

3. **The current `agents/infra/Dockerfile` does not install Terraform** —
   only `pip install fastapi uvicorn pydantic boto3 kubernetes`. There is no
   `terraform` binary on `PATH` inside this container, ever, as currently
   built. `capabilities.terraform` will report `false` regardless of
   `TERRAFORM_BINARY`/`TERRAFORM_DIR` settings.

4. **`/terraform/plan` runs `terraform show -json` — it does not run
   `terraform plan` or `terraform apply`.** It only *displays* an
   already-existing plan file or state; it never generates one. Without a
   `plan_file` that was already created by a real `terraform plan -out=...`
   run, or an initialized state, this call fails outright. **Its output must
   never be treated as evidence that infrastructure has no drift** — it can
   only ever report what's already in a file someone else produced.

5. **Terraform files are mounted read-only**
   (`./infra/terraform:/app/infra/terraform:ro` in `docker-compose.yml`).
   Even if Terraform were installed (Limitation 3), `terraform init`/`plan`
   need to write `.terraform/` and a lock file — both would fail against a
   read-only mount.

6. **The Monitoring Agent's demo pods provide zero real Kubernetes backend
   for the Infra Agent.** `pod-metrics` (§3) is a fake Prometheus exporter,
   not a Kubernetes API server — the Infra Agent's `/k8s/*` endpoints have
   no relationship to it whatsoever and will fail independently of whether
   the monitoring stack is running.

7. **`POST /query` can return an HTTP `200` with an error message as the
   answer, and an empty `sources` array**, rather than an HTTP error code —
   confirmed in `agent.py::ask()`, which catches `InfraClientError`
   internally and returns it as plain text. Only the structured `GET`
   endpoints above (`/aws/instances`, `/k8s/pods`, etc.) return proper
   `503`s on failure — **except `/health/summary`, which always returns
   `200`** even when every backend check fails (by design — see that
   endpoint's description above). Don't treat a `200` from `/query` or
   `/health/summary` as proof the underlying check succeeded — read the
   `answer`/`overall` field.

8. **`/k8s/usage` needs `metrics-server` installed in the target cluster,
   separately from the cluster itself being reachable.** A cluster with a
   perfectly valid kubeconfig but no `metrics-server` add-on will still fail
   this specific endpoint with a `503` ("metrics-server may not be
   installed") while `/k8s/pods`, `/k8s/nodes`, and `/k8s/deployments` on
   the same cluster work fine — they don't need it.

9. **EKS and RDS have real AWS cost implications the other endpoints in
   this agent don't.** `/aws/instances*` calls are free even against an
   account with zero resources (`describe_instances` doesn't cost anything
   to call). An EKS cluster itself costs ~$0.10/hour (~$73/month) with **no
   free tier at all** for the control plane — `/aws/eks` returning data
   means you're already paying for whatever it lists, this endpoint doesn't
   create cost by itself. Testing this agent's AWS calls against a mocked
   backend (`moto`, in `tests/test_infra_agent.py`) or LocalStack Community
   is free; testing against a real EKS cluster is not.

---

## 5. Code Agent — port 8004

Talks to the real GitHub REST API via plain `urllib` (no PyGithub
dependency). Works unauthenticated against public repositories; needs a
token for private repos or a higher rate limit.

### Configuration

```powershell
# In .env:
GITHUB_REPO=owner/repo
GITHUB_TOKEN=ghp_your_token_here
```
`GITHUB_REPO` is required for every endpoint except `/health` — without it,
every other call fails (`503` from structured endpoints, or a `200` with an
explanatory `answer` from `/query`). `GITHUB_TOKEN` needs `repo` scope for
private-repo access and PR/check-run/commit/deployment data; unauthenticated
access is capped at **60 requests/hour** by GitHub, vs. 5,000/hour
authenticated. **The two trigger endpoints below (`rerun`/`dispatch`) need
the token's `workflow` scope specifically** — `repo` scope alone is not
enough to trigger a run, even though it's enough to read one. Recreate the
container after changing either:
```powershell
docker compose --profile full up -d --force-recreate code-agent
```

### `GET /health`

```powershell
Invoke-RestMethod http://localhost:8004/health
```
`{"status","repo","github_token_configured"}` — **this does not test GitHub
access.** It only reports whether `GITHUB_REPO`/`GITHUB_TOKEN` are set, the
same way the Infra Agent's health check doesn't test AWS/K8s connectivity.

### `POST /query`

```powershell
$body = @{ question = "any open PRs?" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8004/query -Method Post -ContentType "application/json" -Body $body
```
Keyword routing (`agents/code/agent.py::ask()`), checked in this order: a
number alongside `"pr"`/`"pull request"`/`"#"` → that PR's CI status;
`"commit"` → 5 most recent commits; `"deploy"` → recent deployments;
`"ci"`/`"pipeline"`/`"workflow"`/`"build"`/`"action"` → latest workflow-run
summary; anything else → open PR count. Same as the Infra Agent: on
failure, this returns HTTP `200` with the error as the `answer` text and
`sources: []`, not an HTTP error code.

**The trigger endpoints (`rerun`/`dispatch` below) are deliberately NOT
reachable through `/query`.** Firing a real GitHub Actions run off a fuzzy
keyword match in free text is exactly the kind of thing that shouldn't
happen by accident — they're only callable through their own explicit
`POST` endpoints.

### `GET /pulls`

```powershell
Invoke-RestMethod "http://localhost:8004/pulls?state=open&limit=10"
```
`{"repo","state","count","pull_requests":[{"number","title","state","author","branch","head_sha","draft","url"}]}`.
`state` is `open` (default), `closed`, or `all`; `limit` is 1–100.
**Use a `number` from this response's `pull_requests` array** for the
`/pulls/{number}` calls below — don't guess a PR number.

### `GET /pulls/{number}`

```powershell
Invoke-RestMethod http://localhost:8004/pulls/1
```
Same shape as above, plus `mergeable` and `merged`. Note: GitHub computes
`mergeable` asynchronously — it can be `null` briefly right after a PR is
opened or updated, not just true/false.

### `GET /pulls/{number}/status`

```powershell
Invoke-RestMethod http://localhost:8004/pulls/1/status
```
`{"number","head_sha","overall": "success"|"failure"|"pending"|"unknown","breakdown","check_runs":[{"name","status","conclusion"}]}`.
**This is a check-runs summary, not a comprehensive merge-readiness
check** — it only reads GitHub's Checks API. CI systems that post to
GitHub's older combined-status API instead of Checks (some third-party CI
tools) won't appear here. It does not account for required reviews, branch
protection rules, or merge conflicts beyond what `mergeable` on the PR
object reports.

### `GET /actions/runs`

```powershell
Invoke-RestMethod "http://localhost:8004/actions/runs?branch=main&status=completed&limit=10"
```
`{"repo","count","workflow_runs":[{"id","workflow_name","branch","status","conclusion","run_number","url","created_at"}]}`.
All three query params are optional.

### `GET /actions/summary`

```powershell
Invoke-RestMethod "http://localhost:8004/actions/summary?branch=main"
```
`{"repo","branch","workflows":[<latest run per workflow name>]}`.

### `GET /commits`

```powershell
Invoke-RestMethod "http://localhost:8004/commits?branch=main&limit=10"
```
`{"repo","branch","count","commits":[{"sha","message","author","date","url"}]}`.
`message` is only the **first line** of the commit message (multi-line
commit bodies are truncated) — use `/commits/{sha}` for the full stats.
`branch` is optional; omitting it uses the repo's default branch.

### `GET /commits/{sha}`

```powershell
Invoke-RestMethod http://localhost:8004/commits/<full-or-abbreviated-sha>
```
Same shape as above, plus `additions`, `deletions`, `files_changed`.

### `GET /deployments`

```powershell
Invoke-RestMethod "http://localhost:8004/deployments?environment=production&limit=10"
```
`{"repo","count","deployments":[{"id","sha","ref","environment","created_at"}]}`.
**This is GitHub's Deployments API — a distinct feature from Actions
workflow runs.** A repo can have a fully working CI pipeline (`/actions/*`
above) and zero entries here, if nothing ever called GitHub's Deployments
API to record one; that's not a bug, most repos (including this one) don't
use this feature at all, which is why this will show `count: 0`.

### `GET /deployments/{deployment_id}/status`

```powershell
Invoke-RestMethod http://localhost:8004/deployments/<id>/status
```
`{"deployment_id","latest_state","statuses":[{"state","description","created_at"}]}`.
Use an `id` from the `/deployments` response above — GitHub deployment IDs
aren't guessable. `latest_state` is whichever status GitHub returns first
(it orders newest-first); a deployment with zero recorded statuses reports
`"unknown"`, not an error.

### `POST /actions/runs/{run_id}/rerun` — **mutating, has a real side effect**

```powershell
Invoke-RestMethod -Uri "http://localhost:8004/actions/runs/<run_id>/rerun?failed_jobs_only=true" -Method Post
```
Actually re-runs a workflow run on GitHub — this shows up as a real new run
attempt in the repo's Actions tab, consumes real CI minutes, and is visible
to everyone with repo access. `failed_jobs_only=true` (default `false`)
reruns only the jobs that failed, not the entire workflow. Get a `run_id`
from `/actions/runs` above. Needs the token's `workflow` scope (see
Configuration above) — a `repo`-scoped-only token gets a `403` here even
though it can read run status fine.

### `POST /actions/workflows/{workflow}/dispatch` — **mutating, has a real side effect**

```powershell
$body = @{ ref = "main"; inputs = @{} } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8004/actions/workflows/ci-cd.yml/dispatch" -Method Post -ContentType "application/json" -Body $body
```
Fires a `workflow_dispatch` event — the GitHub Actions equivalent of
clicking "Run workflow" in the UI. **Only works if the target workflow's
YAML declares `on: workflow_dispatch:`** — this repo's own
`.github/workflows/ci-cd.yml` currently does **not**, so calling this
against `ci-cd.yml` specifically will `422`. The endpoint itself works
against any workflow file that does declare that trigger; nothing here is
broken, this repo's CI file just isn't wired up for manual dispatch.
`workflow` can be the filename (`ci-cd.yml`) or the numeric workflow ID.

### Failure modes to expect

- **Missing `GITHUB_REPO`** → `503` ("GITHUB_REPO is not configured") from
  structured endpoints; a `200` with the same message as `answer` from
  `/query`.
- **Invalid/nonexistent PR number** → GitHub's `404` is caught and
  re-raised as this agent's own error, surfacing as `503` — the original
  GitHub status code is not passed through.
- **Rate limit exceeded** (60/hour unauthenticated, 5,000/hour
  authenticated) → GitHub's `403` rate-limit response surfaces the same way,
  as `503` with GitHub's message in the detail.
- **Empty results** (e.g. `/pulls?state=open` with none open) → a normal
  `200` with `count: 0` and an empty `pull_requests` array — not an error.

---

## 6. Orchestrator — port 8000

### `GET /health`

```powershell
Invoke-RestMethod http://localhost:8000/health
```
`{"status": "ok", "agent": "orchestrator"}`.

### `POST /ask`

```powershell
$body = @{ question = "What should I do when CPU usage is high?" } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8000/ask -Method Post -ContentType "application/json" -Body $body
```

`/ask` invokes the asynchronous LangGraph pipeline: Groq routing (or keyword
fallback), concurrent HTTP agent queries, then Groq synthesis for multiple
successful answers (or labeled-sections fallback). Responses use the
`AskResponse` contract: `answer`, `sources`, `routing`, `results`, `status`,
and `request_id`. Partial failures retain available answers; all-agent failure
returns HTTP 502. Optional `session_id` enables bounded in-process history.

### Calling Infra and Code directly

You can also bypass routing using the agents' own ports — same PowerShell
patterns as §4/§5:

```powershell
Invoke-RestMethod -Uri http://localhost:8003/query -Method Post -ContentType "application/json" -Body (@{ question = "what instances are running?" } | ConvertTo-Json)
Invoke-RestMethod -Uri http://localhost:8004/query -Method Post -ContentType "application/json" -Body (@{ question = "any open PRs?" } | ConvertTo-Json)
```

### What's genuinely unfinished (not just under-documented)

Verified directly against `orchestrator/graph.py` and `orchestrator/router.py`:

- Infra and Code need real backend configuration: a reachable Kubernetes cluster
  and a selected GitHub repository. These cannot be inferred from the migration.
- Conversation history is in-process; multiple orchestrator replicas need
  sticky sessions or a shared memory store.
- Kafka is now integrated as an opt-in transport; production authentication/TLS
  and operational hardening are separate from this local Compose setup.

Multi-agent routing and synthesis support HTTP and opt-in Kafka. Monitoring
implements `/query`; see `validation/agent-integration.md` for current evidence.

---

## 7. End-to-end demonstration

### Fully local — no external accounts needed

```powershell
# 1. Start everything
docker compose --profile full up --build -d

# 2. Confirm every agent is actually responding (not just "container running")
Invoke-RestMethod http://localhost:8000/health   # orchestrator
Invoke-RestMethod http://localhost:8002/health   # monitoring
Invoke-RestMethod http://localhost:8003/health   # infra
Invoke-RestMethod http://localhost:8004/health   # code

# 3. Monitoring demo data (works with zero configuration)
Invoke-RestMethod http://localhost:8002/alerts/summary
Invoke-RestMethod "http://localhost:8002/pods/health?namespace=demo"
```
**Realistic success criteria:** `/health` calls return `200` with
`status: "ok"`. `/alerts/summary` returns a real object — `total`/`active`
may legitimately be `0` if `DemoPodRestarting` hasn't fired yet (it needs
the fake exporter's restart counter to actually exceed the rule's
threshold, and 15s scrape + 15s evaluation delay — see §3). `/pods/health`
should show exactly the two fake demo pods (`api-0`, `worker-0`), not zero
and not more than two — those are the only fixtures the demo exporter
provides.

### Requires `GOOGLE_API_KEY` for embeddings and `LLM_API_KEY` for Groq answers

```powershell
Invoke-RestMethod -Uri http://localhost:8001/ingest -Method Post -ContentType "application/json" -Body (@{ directory = "/app/data" } | ConvertTo-Json)
Invoke-RestMethod -Uri http://localhost:8001/query -Method Post -ContentType "application/json" -Body (@{ question = "What should I do when CPU usage is high?" } | ConvertTo-Json)
```
**Realistic success criteria:** `/ingest` reports `documents_processed`
matching however many `.md`/`.txt` files are actually in `docs\` right now
(2, by default — `runbook-db-connections.md` and `runbook-high-cpu.md` — but
don't hard-code that number if you've added more). `/query` should return
`grounded: true`, a non-empty `sources` array, and a citation like
`[runbook-high-cpu.md]` in the answer text — but the exact wording of
`answer` is not deterministic (it's a live LLM call), so don't expect
byte-identical output between runs.

### Requires AWS credentials

```powershell
Invoke-RestMethod http://localhost:8003/aws/instances/summary
```
Success: a real region and instance count. Without credentials, expect
`503` — that's the Infra Agent working correctly, not a bug (§4,
Limitation 1).

### Requires a real Kubernetes cluster + a properly mounted kubeconfig

```powershell
Invoke-RestMethod http://localhost:8003/k8s/nodes
```
Not achievable with the stock Compose file as shipped — read §4,
Limitation 2, before attempting this.

### Requires Terraform tooling and an existing plan/state artifact

```powershell
Invoke-RestMethod http://localhost:8003/terraform/plan
```
Not achievable in this container as shipped at all — §4, Limitations 3–5.

### Requires a real GitHub repository (`GITHUB_REPO` set)

```powershell
Invoke-RestMethod "http://localhost:8004/pulls?state=open"
Invoke-RestMethod "http://localhost:8004/actions/summary"
```
Success: real data from that repo, rate-limited per §5. Public repos work
without `GITHUB_TOKEN`.

---

## 8. Troubleshooting and development

### Docker Desktop not running

`docker ps` erroring with "cannot connect to the Docker daemon" means Docker
Desktop itself has quit, not just your containers. Relaunch it and wait
30–60 seconds before retrying.

### Port already in use

```
Error: bind: address already in use
```
Something else on the host already owns that port. Find and either stop it
or change the host-side port mapping in `docker-compose.yml`:
```powershell
Get-NetTCPConnection -LocalPort 8001 | Select-Object -Property OwningProcess
Get-Process -Id <OwningProcess>
```
Postgres already deliberately uses 5434 instead of 5432 for exactly this
reason (§1) — the same pattern applies to any other port conflict.

### "Nothing started" after `docker compose up`

You almost certainly forgot `--profile full` — every service in this
Compose file is scoped to that profile; the bare `docker compose up` starts
nothing at all.

### Missing environment variables

FastAPI apps here generally don't crash on a missing optional env var —
they fall back to a default or report the feature as unavailable (§4/§5's
`capabilities`/`repo`/`github_token_configured` fields). `GOOGLE_API_KEY`
and `POSTGRES_PASSWORD` are the two genuinely required values; Postgres
itself will fail to start without `POSTGRES_PASSWORD`.

### Changed `.env` but nothing changed

Env vars are read at container **start**, not live. `docker compose
restart` does not reliably pick up new `.env` values for every setup —
force recreation instead:
```powershell
docker compose --profile full up -d --force-recreate <service>
```

### `503` from an agent endpoint

This means the agent itself is fine but a *backend* it depends on isn't —
read the `detail` field in the response, it's the actual underlying error
(e.g. "Unable to locate credentials", "GITHUB_REPO is not configured",
"Terraform binary 'terraform' was not found on PATH"). Don't assume a `503`
means the container crashed — check `docker compose logs <service>` to
confirm the process is still running.

### Kubeconfig / container path confusion

Covered in full in §4, Limitation 2 — a `KUBECONFIG` path in `.env` is a
path *inside the container*, and nothing in this Compose file currently
puts a real kubeconfig file there.

### Missing Terraform

Covered in §4, Limitation 3 — not installed in this container, full stop,
as currently built.

### Empty monitoring or GitHub results

- Monitoring: `/alerts` returning `{"count": 0}` is a legitimate outcome if
  the demo alert hasn't fired yet (§3's scrape/evaluation delay) — not
  necessarily a misconfiguration.
- GitHub: `/pulls` returning `{"count": 0}` for a repo with genuinely no
  open PRs is correct behavior, not an error.

### Lint and test commands actually supported on this branch

Mirrors exactly what CI runs (`.github/workflows/ci-cd.yml` at the repo
root, not inside `opsbrain/`):

```powershell
pip install -r requirements-dev.txt
ruff check agents\ orchestrator\ shared\
pytest tests\ -v --tb=short
```

**What this covers, and what it explicitly doesn't:**
- `tests\test_rag_agent.py`, `tests\test_ingestor.py` — RAG agent unit
  tests, mocked, no live calls.
- `tests\test_monitoring_agent.py` — Monitoring agent unit tests, mocked.
- `tests\test_database.py` — opt-in, real-database regression, skipped
  without `RAG_TEST_DATABASE_URL`.
- `tests\test_infra_agent.py` — Infra agent's AWS calls (EC2, EKS, RDS,
  aggregate health summary), mocked via `moto` (added to
  `requirements-dev.txt`) — no real AWS account, credentials, or cost
  needed. Does **not** cover the Kubernetes-side methods
  (`list_deployments`, `get_node_resource_usage`, `get_pod_health`,
  `list_nodes`) — those have only been manually verified against a real
  cluster/LocalStack, not unit-tested, since mocking the Kubernetes client
  wasn't done here.
- `tests\test_kafka_client.py` — `shared/kafka_client.py`'s
  serialize/deserialize functions only (round-trips a plain dict and an
  `AgentMessage`). Constructing a real `KafkaProducer`/`KafkaConsumer`
  connects to a broker immediately, so that part is intentionally not
  unit-tested — it was verified manually against the real `kafka`
  container instead (not part of this automated suite).
- **No automated tests exist for the Code Agent in this branch** — no
  `test_code_agent.py`. Its correctness so far has only been verified
  through the manual/live checks documented in §5 and §7 (including a real
  `rerun_workflow` call against this repo's own Actions history), not an
  automated suite. This is a real gap, not an oversight in this document.
- `scripts\validate_rag.py` (§2) is a manual live-integration script, not
  part of the automated `pytest` run.

---

## 9. Architecture, project structure, and roadmap

```
User (CLI / Slack — not built yet)
       │
       ▼
┌──────────────────┐
│   Orchestrator   │  ← forwards /ask to RAG only; multi-agent routing/synthesis unimplemented
│   (port 8000)    │
└────────┬─────────┘
         │  (only this one path is wired up)
         ▼
    ┌────────┐        Direct HTTP calls work, but aren't routed
    │  RAG   │        through the orchestrator yet:
    │ Agent  │        ┌──────────┐  ┌────────┐  ┌──────────────┐
    │ :8001  │        │Monitoring│  │ Infra  │  │    Code      │
    └───┬────┘        │  Agent   │  │ Agent  │  │    Agent     │
        │              │  :8002   │  │ :8003  │  │    :8004     │
     pgvector          └────┬─────┘  └───┬────┘  └──────┬───────┘
     (docs/                 │            │              │
      runbooks)      Prometheus/    AWS/K8s/        GitHub REST
                      Grafana/      Terraform        API
                      Alertmanager
```

### Agent responsibilities — implemented vs. unfinished

| Agent | What's actually implemented | What's not |
|-------|-----------------------------|------------|
| **RAG** | Full ingest → embed (Gemini) → store (pgvector) → retrieve → answer pipeline, with citation validation | Chunking/top-k tuning env vars from `.env.example` don't match the real ones (§2) |
| **Monitoring** | Prometheus/Grafana/Alertmanager integration, `/query`, alert summaries, demo pod health, `/metrics` | No real Kubernetes cluster behind the demo pod metrics |
| **Infra** | Real AWS (boto3: EC2/EKS/RDS), real Kubernetes client (pods/nodes/deployments/resource usage), real Terraform-state-reading logic, an aggregate health-summary endpoint, graceful degradation everywhere, moto-based test coverage for the AWS calls | Kubeconfig isn't actually mountable as shipped; Terraform CLI isn't installed; `/terraform/plan` never generates a plan, only displays one; K8s-side methods have no unit tests, only manual verification |
| **Code** | Real GitHub REST API integration — PRs, commits, deployments, check-run status, Actions runs, and two real mutating actions (rerun a run, dispatch a workflow) | Check-runs only (not the older combined-status API); no test coverage at all; `workflow_dispatch` triggering only works against workflows that declare that trigger (this repo's own CI doesn't) |
| **Orchestrator** | `/health`, `/ask`, Groq routing, concurrent HTTP/Kafka fan-out, synthesis, keyword/labeled fallbacks, bounded session history | Infrastructure/GitHub backend setup remains required; memory is per replica |

### Project structure

```
opsbrain/
├── agents/
│   ├── rag/          ← Groq answers, Gemini embeddings, pgvector retrieval
│   ├── monitoring/   ← fully implemented (against real Prometheus/Grafana/Alertmanager)
│   ├── infra/         ← implemented, with the real limitations in §4
│   └── code/          ← implemented, with the real limitations in §5
├── orchestrator/      ← /health + asynchronous multi-agent /ask
├── shared/             ← shared chat factory, models, observability and integrated Kafka request/reply
├── infra/terraform/  ← Terraform IaC definitions (not yet applied to any real AWS account)
├── infra/prometheus/, infra/grafana/, infra/alertmanager/ ← real local monitoring stack config
├── k8s/                ← Kubernetes manifests referencing ECR image paths (not GHCR — not yet updated for the current image registry)
├── tests/              ← RAG, Monitoring, Infra, observability, chat migration and Kafka request/reply tests
├── scripts/validate_rag.py ← manual live-integration script (see §2)
├── .github/            ← does not exist under opsbrain/ — the real CI workflow lives at the repo root
├── docker-compose.yml
├── .env.example
└── README.md            ← this file
```

### Roadmap (honest state, not aspirational)

- [x] RAG Agent — Gemini embeddings with Groq-backed answers
- [x] Monitoring Agent — real Prometheus/Grafana/Alertmanager integration
- [x] Infra Agent — real AWS (EC2/EKS/RDS)/K8s (pods/nodes/deployments/usage)/Terraform-reading logic, an aggregate health summary, with documented setup gaps
- [x] Code Agent — real GitHub PR/commits/deployments/Actions integration, plus two real mutating actions (rerun a run, dispatch a workflow)
- [x] Kafka producer/consumer — real `kafka-python`-backed client in `shared/kafka_client.py`, verified against a live broker
- [x] CI pipeline — lint, test, build, and publish images to GHCR (see the repo-root `.github/workflows/ci-cd.yml`); the `deploy` stage's working-directory bug is fixed, though it still can't succeed end-to-end until the next item below is done
- [x] Orchestrator HTTP/Kafka routing and synthesis (live RAG+Monitoring verified; full backend setup still required)
- [x] Opt-in Kafka workers and orchestrator request/reply integration
- [x] `/metrics` endpoints, Grafana dashboards, Loki logging, and alert rules (OPU-56)
- [x] Optional kubeconfig mounting via `docker-compose.kubernetes.yml` (real cluster still required)
- [ ] Terraform CLI installed in the Infra Agent's image (§4, Limitation 3)
- [ ] Automated test coverage for the Code Agent, and for the Infra Agent's Kubernetes-side methods (AWS-side is covered via `moto`)
- [ ] Real AWS EKS deployment via Terraform + ArgoCD — Terraform definitions exist under `infra/terraform/` but have not been applied to any real account, and the CI `deploy` stage's `ARGOCD_SERVER`/`ARGOCD_TOKEN` secrets can't be filled in with real values until an EKS cluster + ArgoCD install actually exist
