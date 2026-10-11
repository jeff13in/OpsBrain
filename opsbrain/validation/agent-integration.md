# Selective monitoring and Kafka integration

Integrated from `origin/jeffin-dev`, commit `21135ef`, without a wholesale merge.
Preserved the current Groq model factory, separate router/synthesis injection,
10s/20s deadlines, no provider retries, Gemini embeddings, RAG generation and
ingestion, response contracts and observability. The chat/embedding implementation
files have no diff in this change. HTTP remains the default.

## Implemented

- Monitoring `/query`: alert, pod-health and scrape-target answers using existing
  real backends; backend failures return non-success status codes.
- Kafka request/reply bus and all four agent workers, with correlated envelopes,
  startup readiness, malformed/expired-request handling and bounded publishing.
  The worker invokes the same validated ASGI `/query` handler as HTTP; transport
  errors retain the existing retries, partial answers and metrics.
- Optional `docker-compose.kafka.yml` enables Kafka across the stack and waits
  for broker health. Base Compose still selects HTTP and retains all LLM settings.
- Optional `docker-compose.kubernetes.yml` mounts a user-selected kubeconfig;
  it does not provision a cluster or manufacture credentials.
- Runtime images include Kafka and HTTP-client dependencies. Regression and
  transport validation scripts/documentation are updated.

## Verification

Recorded October 10, 2026 (America/Toronto; JSON timestamps use UTC).

| Check | Result |
|---|---|
| Full regression suite with local pgvector test enabled | **124 passed**, no skips, 33.68s; 219 upstream warnings |
| Ruff across agents/orchestrator/shared/scripts/tests | Passed |
| `git diff --check` | Passed; line-ending normalization warnings only |
| Rebuild and start all local agents | Passed |
| Kafka image/broker health and opt-in Compose config | Passed |
| Live HTTP transport smoke | **7/7 passed**, `integration-http-results.json` |
| Live Kafka transport smoke | **7/7 passed**, `integration-kafka-results.json` |
| Full live provider/HTTP suite | **14 passed, 3 failed**, `integration-full-results.json` |

Each transport smoke checks all five `/metrics` endpoints and two deployed
`/ask` requests: monitoring-only, and real RAG + monitoring fan-out followed by
Groq synthesis. These are live provider/backend checks, not synthetic summaries.
The strict checks require LLM routing, expected agent sets, successful workflow
status, synthesis instead of labeled fallback, and every source citation.
Kafka requests completed in 1.719s and 5.203s respectively. The Kafka-mode
orchestrator was inspected and still constructed `openai/gpt-oss-20b` and
`qwen/qwen3.8-27b`. RAG answer configuration remains `openai/gpt-oss-120b`.

After testing, the agents were recreated in **HTTP** mode, the HTTP smoke was
rerun successfully, and the temporary Kafka broker was stopped. Its data volume
is retained. Existing Postgres/runbook data was not deleted or reingested by
these transport smoke tests. No secrets are included in these evidence files.

Commands from `opsbrain/`:

```powershell
docker compose --profile full up --build -d orchestrator rag-agent monitoring-agent infra-agent code-agent
python -m scripts.validate_transport --transport http --output validation/integration-http-results.json
docker compose -f docker-compose.yml -f docker-compose.kafka.yml --profile full up -d orchestrator rag-agent monitoring-agent infra-agent code-agent
python -m scripts.validate_transport --transport kafka --output validation/integration-kafka-results.json
docker compose --profile full up -d orchestrator rag-agent monitoring-agent infra-agent code-agent
docker compose --profile full stop kafka
```

Full provider validation used the existing `scripts.validate_chat`, securely
loading `.env` and setting host agent URLs; `--output` kept prior migration
evidence separate. Full regression tests securely supplied
`RAG_TEST_DATABASE_URL`; their temporary schema changes were rolled back.

## Remaining backend setup, not chat migration regressions

The full suite now passes monitoring. The remaining three failed checks are
infra-only (no Kubernetes configuration), code-only (`GITHUB_REPO` unset),
and the all-four workflow (partial because those two agents are unavailable).
The combined answer retains RAG + monitoring evidence and reports both missing
agents. No configuration failure is relabeled as a success.

The user must select which GitHub repository to inspect and provide a reachable
Kubernetes cluster/kubeconfig. This checkout's remote is `jeff13in/OpsBrain`;
it was not automatically assigned as the Code Agent's target. The kubeconfig
override is supplied but not live-verified against a real cluster. No branch
integration can supply those user-specific backend credentials. Production
Kafka authentication, durability/idempotency hardening and Kubernetes deployment
are outside the verified local transport checks.
