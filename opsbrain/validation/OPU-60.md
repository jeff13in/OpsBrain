# OPU-60: serialization, timeout and failure handling

Latest child-task verification: OPU-61 completed with **217 full regression
tests passed**, no skips, and **8/8 real-Kafka checks** using the actual RAG/
Monitoring query handlers with explicitly injected backends. See `OPU-61.md`
and `opu61-live-results.json`. The original OPU-60 results below are historical
evidence, not the latest combined suite count.

Implemented and verified on `joint`, based on `52044e9`. Report timestamp:
`2026-10-11T04:01:23.962278+00:00` (UTC).

Existing Kafka/agent/orchestrator integration and OPU-62 were already present;
no wholesale branch merge was needed. This change closes remaining resilience
gaps while preserving the current chat/embedding setup and HTTP default.

## Added hardening

- Reject invalid UTF-8/JSON, non-object messages and non-finite JSON numbers.
- Validate finite positive deadlines, nonempty correlation/topic identifiers,
  known agent names and actual HTTP status codes in Kafka envelopes.
- Catch per-record consumer handler errors and continue consuming; do not log
  raw payloads or exception text for these errors.
- Return safe 500 failure envelopes for unexpected agent exceptions or results
  that cannot serialize, rather than silently losing the reply.
- Match replies to both correlation ID and expected agent. Ignore malformed,
  mismatched, unknown/duplicate/late replies and tolerate closed request loops.
- Cancel/clean pending futures; release inflight requests on shutdown or reply
  consumer failure. Keep startup/publish/reply waits bounded.
- Add HTTP wall-clock agent deadlines and bounded-status logging, retaining
  one retry for retryable non-timeout failures and no retries for timeouts.
- Test mixed four-agent success/invalid response/timeout/failure aggregation,
  real Infra/Code ASGI handlers over the serialized in-memory Kafka transport,
  and continued healthy processing after malformed or failed messages.

## Verification

| Check | Result |
| --- | --- |
| Full pytest suite, including local pgvector rollback test | **181 passed**, no skips, 37.80s |
| Ruff across agents/orchestrator/shared/scripts/tests | Passed |
| HTTP and Kafka Compose config validation | Passed |
| `git diff --check` | Passed; line-ending warnings only |
| Real Kafka resilience validator | **6/6 passed**, 7.136s |

The full suite emits 219 upstream deprecation warnings. Tests are run from
`opsbrain/` with `.venv/Scripts/python.exe`; the local database URL was securely
derived from `.env` without displaying secrets. Temporary test DB objects were
rolled back. See `tests/test_pipeline_resilience.py`, `test_agent_bus.py`,
`test_agent_failures.py` and `test_llm_migration.py` for failure/model coverage.

## Real broker evidence

`scripts/validate_resilience.py` runs against a real local Kafka broker with
explicitly synthetic FastAPI agents and no LLM/GitHub/AWS/Kubernetes calls:

1. Poison wire/schema messages do not stop a healthy worker.
2. Parallel invalid response, absent-agent timeout and 500 failure retain the
   successful agent's answer, citation and partial status.
3. An agent returns healthy answers after an injected failed response.
4. Eight simultaneous requests retain their own correlated replies.
5. A wrong-agent reply cannot complete the pending request.
6. Shutdown releases a pending request instead of waiting its 60s deadline.

Evidence: `opu60-live-results.json`. Topics/groups are isolated under
`opsbrain.validation.709713c48047.`; small test messages remain in the retained
local Kafka volume. No operational consumer groups/messages were consumed.
The broker was temporarily started and then stopped to restore its prior state.
Operational agents were not recreated, and remain in their existing HTTP mode.

The validator was run in a temporary `opsbrain-orchestrator` image container on
`opsbrain_default`, with this branch mounted read-only at `/verification`,
`validation/` mounted at `/evidence`, `PYTHONPATH=/verification` and
`KAFKA_BOOTSTRAP_SERVERS=kafka:9092`:

```text
python /verification/scripts/validate_resilience.py --output /evidence/opu60-live-results.json
```

## Preserved flow and limitations

Groq factory/models, routing decisions, separate synthesis injection, 10s/20s
router/synthesis deadlines, disabled provider retries, Gemini embeddings, RAG
ingestion/retrieval, `/ask` contract, source aggregation and HTTP default remain.
Shared chat, orchestrator LLM/main, RAG implementation, Compose and `.env.example`
have no diff in this change. Agent time budgets are unchanged; HTTP now enforces
the same wall-clock budget already used by Kafka.

Native synchronous work already running in a thread cannot be forcibly killed
by cancelling its awaiter. Late results are ignored; valid requests still follow
their original agent endpoints. This work does not add exactly-once delivery,
production Kafka TLS/ACLs or provision missing backend credentials.

Real GitHub/AWS/Kubernetes backend acceptance remains deferred as previously
requested. OPU-62's failure handling is verified separately in `OPU-62.md`.
