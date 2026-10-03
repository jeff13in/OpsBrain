# Orchestrator contract (OPU-42)

How the Orchestrator and the four agents talk to each other. Models live in
`shared/models.py`; rules live in `orchestrator/contract.py` and
`orchestrator/router.py`; tests in `tests/test_orchestrator_contract.py` and `tests/test_orchestrator_graph.py`.

## Request flow

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
- With `GOOGLE_API_KEY` set, a Gemini classifier routes (`method="llm"`) and rewrites
  follow-ups using the session history. Any LLM failure, unparseable reply, or empty/unknown
  agent list falls back to keyword routing. Without a key, routing is always by keyword.
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

## 6. Conversation memory

Pass the same `session_id` on each `/ask` to keep context. The last 6 question/answer pairs
are kept per session, sessions expire after 1h idle, and at most 1000 are held (least
recently used are evicted). Failed (`error`) turns aren't remembered.

## Known gaps in the agents (to fix before OPU-44 / OPU-50)

1. **Monitoring has no `/query` endpoint.** It needs one that returns `AgentReply` (Rifat's code).
2. **Infra and Code `ask()` return errors as 200s.** `InfraClientError`/`CodeClientError`
   come back as `{"answer": "<error text>"}`, so the Orchestrator counts them as successes.
   They should raise 503 instead (OPU-62).
3. **RAG's `/query` requires `question` ≥ 5 characters.** Shorter questions get a 422, which maps to `bad_request`.
4. **Memory is per process.** `k8s/orchestrator.yaml` runs 2 replicas, so a session's next
   turn can land on a pod that never saw it. This needs sticky sessions or a shared store
   (Postgres/Redis) before deploying (OPU-54).
5. **`k8s/orchestrator.yaml` still passes `OPENAI_API_KEY`.** The orchestrator now uses
   `GOOGLE_API_KEY` (OPU-54).
