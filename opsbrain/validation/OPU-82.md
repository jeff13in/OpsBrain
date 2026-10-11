# OPU-82 acceptance check

The implementation is already present from OPU-80: `agents/rag/agent.py`
constructs `get_chat_model("answer")`; its default model is
`openai/gpt-oss-120b`. Gemini embedding configuration, ingestion, vector schema
and stored documents remain unchanged. No additional production changes were
needed during this acceptance-check turn.

## Executed verification

From `opsbrain/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_rag_agent.py tests/test_llm_migration.py -q
```

Result: **37 passed**, one upstream LangGraph deprecation warning, 11.16s.
These are offline tests, not live Groq integration results. They cover the
high-CPU and database-connection questions, expected bracketed runbook citations,
grounded metadata, unchanged embedding model, answer-role selection, and
single-request SDK 429 fallback preserving retrieved evidence.

## Live acceptance blockers

Fresh environment checks found:

- `LLM_API_KEY`, `GOOGLE_API_KEY`, `DATABASE_URL`, and `RAG_TEST_DATABASE_URL`
  are not configured in this process. Values were not displayed.
- No `opsbrain/.env` is present.
- `docker info` outside the sandbox cannot reach Docker Desktop's Linux engine
  pipe; Docker is not running/available.
- `http://localhost:8001/health` is unavailable.

On the subsequent request to run live checks, both documented
`scripts.validate_rag` commands were executed: the high-CPU command and the
database-connections command each exited 1 with `FAIL: URLError`. Both stopped
at the RAG API health request, before ingestion or provider calls. Docker and
credential preflight checks were repeated with the same unavailable results.

Consequently `scripts/validate_rag.py` cannot currently pass against real
services. Live ingestion, persisted-vector, Groq answer and grounding checks
were not reached; no ingestion or database writes occurred.
Do not mark OPU-82 complete based on mocked tests alone.

Latest retry: Docker is now available (`29.7.2`), but `docker ps` shows no running
containers. The RAG health endpoint remains unreachable; `.env` and process
credentials/database URL remain absent. Both live validators were rerun and
again exited 1 with `FAIL: URLError`, before ingestion or provider calls.
Starting Docker resolves only the engine prerequisite, not service configuration.

## Resume verification

Start Docker Desktop and configure the local `.env` with the settings documented
in README, including the Groq key, Google embedding key and database password.
Never put secrets in a ticket or chat. Then, from `opsbrain/`:

```powershell
docker compose --profile full up --build -d rag-agent
```

For the host-side validator, securely export `DATABASE_URL` pointing to the
intended Compose database on host port 5434, then run:

```powershell
$env:PYTHONPATH = ".;agents"
python -m scripts.validate_rag --directory docs --api-directory /app/data
python -m scripts.validate_rag --directory docs --api-directory /app/data --question "How do I handle exhausted database connections?" --expected-source runbook-db-connections.md
```

The validator reingests bundled runbooks twice and replaces those sources'
existing chunks. Use the intended local test database. Both commands must pass
to establish live acceptance for the two required runbook questions.
