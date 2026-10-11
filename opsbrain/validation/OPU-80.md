# OPU-80 implementation and validation evidence

Recorded October 10, 2026 (America/Toronto; live report timestamp is UTC).
Branch: `rifatchowdhury619/opu-80-switch-opsbrain-chat-models-from-gemini-to-groq`.

Implementation and provider-level live validation now pass. OPU-80 is **not ready
to mark complete**: the full OPU-51 multi-agent acceptance still has failures.
The latest results below supersede historical unavailable-service checks.

## Latest live run: October 10, 2026 (America/Toronto)

`validation/opu80-live-results.json` records timestamp
`2026-10-11T02:46:33.675349+00:00`. `scripts.validate_chat` exited 1 with
**13 passed checks, 4 failed checks**, all against live providers/local services:

- Authenticated Groq model discovery passed for all three configured models.
- All six routing cases passed with schema-valid decisions and expected agent
  sets; measured routing times ranged from 0.312 to 0.531 seconds.
- Both RAG API checks passed with grounded metadata, expected citations and
  no extractive fallback detected.
- Real Qwen synthesis over explicitly labeled fixture summaries passed;
  `[runbook-high-cpu.md]`, `[kubernetes:pods]` and unavailable-code reporting
  were retained. This is real provider inference but not live backend evidence
  for the synthetic summaries.
- Both RAG-only async pipeline cases and deployed `/ask` passed.
- Monitoring-only, infra-only, code-only and all-four pipeline cases failed.
  All-four retained the successful RAG answer with `partial` status.

Read-only diagnostic queries confirmed the remaining backend causes:
monitoring `/query` returns 404; infra `/query` returns 500 because no Kubernetes
configuration is available; code `/query` returns 500 because `GITHUB_REPO` is
unset. Kafka is still not connected on this branch. No alternate branches were
merged, no operational write commands were executed against AWS/Kubernetes/GitHub,
and no failure was converted into a fabricated success.

Both `scripts.validate_rag` commands (high CPU and DB connections) separately
exited 0. Each verified ingestion twice: 3 documents, 14 exact nonzero
3072-dimensional vectors; both queries returned 4 chunks, `grounded: true`,
empty validation errors and the expected citation. See `OPU-82.md`.

Live commands ran from `opsbrain/`: securely load `.env`, set host agent URLs
to ports 8001–8004, and run the documented validators. The host RAG validator
used the Compose database at port 5434. All five agents passed `/health`;
Postgres and Prometheus were healthy. The local services remain running for
further validation. The created database is local, and only mounted bundled
runbooks were ingested. Earlier statements about no DB writes describe the
initial implementation turn, not this subsequent live-validation run.

429/no-retry and deadline cancellation remain deterministic mocked checks;
the live run did not intentionally exhaust account limits or simulate failures
against the external providers. Ollama and Kubernetes rollout remain untested.

The full regression suite was rerun with `RAG_TEST_DATABASE_URL` securely
constructed for the local database: **96 passed**, no skips, 19.94s, with 219
upstream deprecation warnings. The real pgvector schema/cosine-search regression
used a temporary schema and rolled back every test-created object/row.
`git diff --check` passed (line-ending normalization warnings only).

## Models and compatibility

| Role | Model | Timeout | Completion cap |
|---|---|---|---|
| Router | `openai/gpt-oss-20b` | 10s wall-clock deadline | 1024 |
| RAG answer | `openai/gpt-oss-120b` | 45s HTTP timeout | 2048 |
| Synthesis | `qwen/qwen3.8-27b` | 20s wall-clock deadline | 1536 |

The exact Qwen identifier was checked against the official
[Groq catalog](https://console.groq.com/docs/models) on October 10, 2026. It is a
preview model, not a production availability guarantee. Account-specific model
access must still be checked with authenticated `/models`.

All roles share `ChatOpenAI`, Chat Completions, temperature zero, and
`max_retries=0`. Ollama construction is tested with a local URL, nonempty dummy
key and locally named models; actual Ollama inference is not tested.
Google embeddings remain `models/gemini-embedding-001`, with existing 3072
dimensions, ingestion, vector schema and stored-document behavior unchanged.
No migration, ingestion or database writes were performed during this work.

## Executed commands and results

Commands below run from `opsbrain/` using the installed `.venv` (Python 3.11).

| Command | Result |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest -q` | **95 passed, 1 skipped**, 28.55s; 219 upstream LangGraph/Kafka deprecation warnings |
| `.\.venv\Scripts\ruff.exe check agents orchestrator shared scripts tests` | Passed |
| `.\.venv\Scripts\python.exe -m pip check` | Passed: no broken requirements |
| `git diff --check` | Passed; line-ending normalization warnings only |
| `docker compose --profile full config --quiet` | Passed syntax/interpolation; missing local secrets and Docker config access warnings |
| `.\.venv\Scripts\python.exe -m scripts.validate_chat` | **Not executed**: missing `LLM_API_KEY`; report declares exit code 2, recorded in `opu80-live-results.json` |
| `$env:PYTHONPATH='.;agents'; .\.venv\Scripts\python.exe -m scripts.validate_rag --directory docs --api-directory /app/data` | Failed preflight: `URLError` contacting the local RAG API; ingestion/vector/query checks not executed |

The skipped database test requires `RAG_TEST_DATABASE_URL`. Docker's engine pipe
was unavailable, so image builds, container startup and Kubernetes rollout were
not executed. No populated local `.env` was present. Installed versions include
langchain-openai 0.3.35, langchain-core 0.3.86, langchain-google-genai 2.1.12 and
langgraph 0.6.11. Dependencies are constrained to the existing core 0.3 family.

An initial test run found seven incorrect new fallback test questions (the
existing keyword matcher does not recognize bare plural `pods`) and a
pre-existing zero-TTL memory test sensitive to Windows clock resolution. Test
questions now include `Kubernetes`; the memory test uses a controlled clock.
Neither routing keywords nor production memory behavior was changed.

## Mocked provider/pipeline evidence (not live Groq)

`tests/test_llm_migration.py` uses both fake models and the actual
LangChain/OpenAI SDK with `httpx.MockTransport`:

- Every role respects its environment-selected model, timeout and retry setting;
  invalid roles/blank settings/credential-bearing URLs fail without secret text.
- An actual mocked Chat Completions JSON body validates against the router schema,
  deduplicates agents and preserves registry order. Fenced JSON and existing
  follow-up rewrite tests also pass; invalid schema selects the keyword fallback.
- Router HTTP 429 with `Retry-After: 60` makes exactly one SDK request and the
  graph returns its keyword-routed answer in under one second. This excludes real
  network latency, so it establishes fallback overhead, not provider latency.
- Controlled router/synthesis deadlines cancel the blocked coroutine and select
  existing fallbacks. Tests shorten the deadline to 0.01s, then assert production
  constants remain 10s/20s.
- High-CPU and database-connection questions retain expected bracketed filenames,
  `grounded=true`, source lists, retrieval counts and full supplied evidence in
  the answer prompt. Invalid citations/empty responses retain validation behavior.
- RAG SDK HTTP 429 makes one request and returns grounded source snippets.
- Successful synthesis keeps `[runbook-high-cpu.md]` and `[kubernetes:pods]`,
  plus explicit `Unavailable: code (unavailable)` even if the model omits them.
- Synthesis 429/timeout/provider error/empty text returns labeled `[rag]`/`[infra]`
  sections, preserves source metadata and reports unavailable code; partial
  status is unchanged. Mocked 429 makes one SDK request without backoff.
- Four mocked HTTP agents are simultaneously in flight (`peak == 4`); distinct
  router and synthesis models are called once each. Existing `/ask`, retries,
  session memory and partial-failure tests pass.

## OPU-51 question set and live checks

`opu51-questions.json` records six explicit cases: high CPU, exhausted database
connections, active alerts, Kubernetes pods, open pull requests, and an all-four
high-CPU investigation. Original OPU-51 questions/results were not present in the
checkout or Linear issue/comments; this is a **reconstructed** coverage set,
not a claim to reproduce an unavailable historical suite.

`scripts/validate_chat.py` records model discovery, routing decisions/timing,
both real RAG API answers, real synthesis over clearly labeled fixture summaries,
the real asynchronous HTTP agent graph, and deployed `/ask` response validation.
All live cases are currently **not executed**. The companion
`opu80-live-results.json` records the credential preflight, not fabricated answers.
Run the live commands in README after securely providing keys and starting APIs.
The existing RAG validator additionally reingests bundled runbooks twice and
checks persisted 3072-dimensional vectors; run it only against the intended DB.

Existing OPU-51 scope includes Kafka-connected agents. This checkout implements
HTTP fan-out; no agent/orchestrator imports the Kafka client. Monitoring also
lacks `/query`, so monitoring-only/all-four real pipeline cases cannot pass as
shipped. Implementing those adapters is outside this provider migration; do not
silently treat partial HTTP success as full OPU-51/Kafka acceptance.

## Changed files

Created: `shared/llm.py`, `tests/test_llm_migration.py`,
`scripts/validate_chat.py`, `k8s/chat-config.yaml`,
`validation/opu51-questions.json`, `validation/opu80-live-results.json`, this file.

Updated: `orchestrator/{llm.py,graph.py,main.py,Dockerfile,CONTRACT.md}`,
`agents/rag/{agent.py,Dockerfile,main.py}`, `requirements-dev.txt`,
`docker-compose.yml`, `k8s/{orchestrator.yaml,rag-agent.yaml}`, `.env.example`,
`README.md`, `scripts/validate_rag.py`,
`tests/{test_rag_agent.py,test_orchestrator_graph.py}`, `shared/observability.py`.
RAG main import ordering and observability whitespace are lint-only corrections.

## Remaining risks

Groq free capacity is not unlimited: the published GPT-OSS and Qwen allowance is
200K tokens/day and 8K tokens/minute per model, subject to account exceptions
([official limits](https://console.groq.com/docs/rate-limits)). At an illustrative
3,300 tokens/answer this is about 60 answers/day. No prompt evidence is truncated
by this migration, so large evidence/history can still exhaust those budgets.
Reasoning tokens can consume completion caps and produce empty/incomplete prose.
Preview model lifecycle, account permissions, real latency, Ollama quality and
provider-specific payload compatibility require live confirmation. K8s database
configuration and existing operational backend setup remain deployment prerequisites.
