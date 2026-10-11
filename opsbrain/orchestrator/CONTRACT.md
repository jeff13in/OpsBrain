# Orchestrator contract (OPU-42)

How the Orchestrator and the four agents talk to each other. Models live in
`shared/models.py`; rules live in `orchestrator/contract.py` and
`orchestrator/router.py`; tests in `tests/test_orchestrator_contract.py` and `tests/test_orchestrator_graph.py`.

## Request flow

HTTP remains the default. With `AGENT_TRANSPORT=kafka`, `shared/agent_bus.py`
publishes an `AgentQuery` envelope to `opsbrain.agent.<agent>.requests` and matches
correlated replies from `opsbrain.agent.replies`. Each worker invokes the same
`/query` ASGI handler, preserving validation and HTTP-equivalent status/body.
Both transports retain execution metrics, agent retries and partial-answer rules.
The reply listener must be ready before publishing; deadlines also bound sends.
Transport selection does not change any chat model, embedding or provider retry.

```
POST /ask  AskRequest{question, session_id?}
  → route       RoutingDecision{agents, method, reason} + standalone question
  → call_agent  one parallel branch per routed agent (LangGraph Send) → one AgentResult each
  → synthesise  status + answer + merged sources
  ← AskResponse
```

## 1. Orchestrator state

`OrchestratorState` in `orchestrator/graph.py`:

| Field | Set by | Notes |
|---|---|---|
| `request_id`, `session_id`, `question` | `/ask` | `session_id` keys conversation memory |
| `history` | `/ask` | prior turns, `{"role", "content"}`, from `SessionMemory` |
| `agent_question` | route | follow-up rewritten to stand alone ("did it break them?" → "Did PR #42 break the api pods?"); this is what agents receive |
| `routing` | route | `RoutingDecision` |
| `results` | call_agent | `list[AgentResult]`, **append reducer** so parallel branches don't overwrite each other |
| `status`, `final_answer`, `sources` | synthesise | |

## 2. Routing contract

- `route()` always returns at least one agent; nothing matched → `rag` (`method="fallback"`).
- Agents are returned in registry order: `rag, monitoring, infra, code`.
- Keyword match is whole-word (`pr` doesn't match `prometheus`).
- With `LLM_API_KEY` set, `get_chat_model("router")` classifies (`method="llm"`)
  and rewrites follow-ups using session history. Its default is Groq
  `openai/gpt-oss-20b`. Calls have a 10-second wall-clock deadline and zero SDK
  retries. HTTP 429 immediately falls back to keywords, without backoff (under
  one second of fallback overhead after the error is received). Timeout,
  malformed JSON, invalid schema, and empty/unknown agent lists also fall back.
- `LLM_BASE_URL` selects an OpenAI-compatible Chat Completions endpoint. All
  three roles use the shared factory in `shared/llm.py`; model names are
  configured independently with `LLM_MODEL_ROUTER`, `LLM_MODEL_ANSWER`, and
  `LLM_MODEL_SYNTH`. Invalid/missing chat settings enable deterministic fallback.
- Each agent has a URL (overridable via `<NAME>_AGENT_URL`) and timeout in `AGENT_REGISTRY`
  (RAG 60s, others 30s).

## 3. What every agent must implement

`POST /query` with body `AgentQuery{question, request_id}` (extra fields may be ignored).

On success, HTTP 2xx with at least:

```json
{"answer": "string", "sources": ["string"], "data": {"optional": "structured payload"}}
```

Extra top-level fields are allowed and land in `AgentResult.data`.

On failure, **return a non-2xx status**, don't put the error into `answer`:
- 4xx: bad input (not retried)
- 503: a dependency is down, e.g. Prometheus or the GitHub API (retryable)
- other 5xx: a bug (not retried)

## 4. Error paths

Every agent call ends in an `AgentResult`; the Orchestrator never raises because one agent failed.

| What happened | `status` | `error.code` | retryable |
|---|---|---|---|
| no reply before timeout | `timeout` | `timeout` | yes |
| connection refused / DNS / HTTP 503 | `error` | `unavailable` | yes |
| HTTP 4xx | `error` | `bad_request` | no |
| other HTTP 5xx | `error` | `agent_error` | no |
| 2xx but no `answer` field or not JSON | `error` | `invalid_response` | no |

Retryable failures other than `timeout` get **one** retry. A timeout already used up the
agent's whole time budget, so it isn't retried.

## 5. Aggregation rules

- **status**: all routed agents ok → `ok`; at least one → `partial`; none → `error`.
- **HTTP**: `/ask` returns 200 for `ok`/`partial`, 502 for `error`. The body is always `AskResponse`.
- **sources**: from successful agents only, in routing order, de-duplicated.
- **answer**:
  - one successful agent and no failures: its answer verbatim (no LLM call);
  - two or more successful agents: LLM synthesis, or `fallback_answer()` if there's no key or the call fails;
  - anything else (one success plus failures, or no successes): `fallback_answer()`, which gives
    one `[agent]` section per success plus an `Unavailable: …` line.
- **results** are listed in routing order, whatever order the parallel calls finished in.

Synthesis uses `get_chat_model("synth")`, default `qwen/qwen3.8-27b`, with a
20-second wall-clock deadline and zero retries. HTTP 429, timeout, empty replies,
and provider failures return `fallback_answer()`'s existing labeled sections.
Successful synthesis retains known source citations and a deterministic
unavailable-agent line even if the model omits them. The response contract and
per-agent HTTP retry policy above are unchanged.

RAG chat uses `get_chat_model("answer")`, default `openai/gpt-oss-120b`, with
a 45-second request timeout and no retries. Missing settings/provider failures
use retrieved snippets. `grounded` describes retrieval/citation validation, not
proof that the chat provider generated the answer. Gemini embeddings remain
`models/gemini-embedding-001` and 3072-dimensional; no schema or ingestion changes.

## 6. Conversation memory

Pass the same `session_id` on each `/ask` to keep context. The last 6 question/answer pairs
are kept per session, sessions expire after 1h idle, and at most 1000 are held (least
recently used are evicted). Failed (`error`) turns aren't remembered.

## Known gaps in the agents (to fix before OPU-44 / OPU-50)

1. **Monitoring `/query` is integrated.** Alerts, pod health and scrape targets
   return `AgentReply`-compatible answers over HTTP or opt-in Kafka. Backend
   failures remain 503 rather than successful error prose.
2. ~~**Infra and Code `ask()` return errors as 200s.**~~ Fixed in OPU-62. `/query` now returns
   503 when the backend is down, slow or throttled, 404/400 for things that don't exist or bad
   input, and 500 when credentials, permissions or config are missing. Backend calls are bounded
   so each agent replies within the Orchestrator's 30s budget: AWS 5s to connect, 20s to read,
   2 attempts; Kubernetes 20s per request; GitHub 10s per request; Infra's health summary runs
   its 6 checks at the same time.
3. **RAG's `/query` requires `question` ≥ 5 characters.** Shorter questions get a 422, which maps to `bad_request`.
4. **Memory is per process.** `k8s/orchestrator.yaml` runs 2 replicas, so a session's next
   turn can land on a pod that never saw it. This needs sticky sessions or a shared store
   (Postgres/Redis) before deploying (OPU-54).
5. **Deployment secrets:** the orchestrator and RAG use `LLM_API_KEY` from
   `opsbrain-secrets/llm-api-key`; RAG also needs
   `opsbrain-secrets/google-api-key` for unchanged Gemini embeddings. Apply
   `k8s/chat-config.yaml` before deploying the updated images.
