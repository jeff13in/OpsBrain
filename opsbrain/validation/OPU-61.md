# OPU-61: RAG/Monitoring serialization and failure handling

Completed on `joint`. OPU-61 had no description beyond its title, so scope was
derived from the RAG/Monitoring flows and OPU-60's parent resilience requirements.
OPU-60's shared transport hardening is retained; see `OPU-60.md`.

## Implementation

- RAG validates response fields before returning success, including nonempty
  answers, valid sources/grounding fields and nonnegative retrieval counts.
  Missing/malformed output returns a safe 500, not a validation crash or 400
  incorrectly suggesting the user's request was invalid.
- RAG dependency runtime, connection/read timeout and PostgreSQL connection
  failures return safe 503 responses. Unexpected query failures return safe 500.
- Monitoring validates the shared AgentReply contract and JSON serialization,
  including rejecting empty answers, non-finite numbers and unsupported objects.
- Monitoring dependency outages/timeouts return safe 503; backend crashes and
  malformed output return safe 500. Error logs include exception classes, not
  backend exception text or payloads.
- Valid query responses preserve answer text, citations, sources, grounded
  metadata, retrieval counts and topic data. Existing input validation is kept.
- Existing Kafka transport cleanup/retry/deadline behavior is unchanged. Tests
  cover recovery after repeated outage replies, and partial RAG/Monitoring
  aggregation when one real handler returns invalid output.

## Verification

| Check | Result |
| --- | --- |
| Targeted RAG/Monitoring/model migration suites | **90 passed**, 22.88s |
| Full regression suite with real local pgvector rollback test | **217 passed**, no skips, 49.40s |
| Ruff across agents/orchestrator/shared/scripts/tests | Passed |
| Real Kafka with actual RAG/Monitoring query handlers | **8/8 passed**, 7.451s |

The test suite emits 219 upstream deprecation warnings. New coverage is in
`tests/test_rag_monitoring_failures.py`; full tests include OPU-60/62 and model
factory/deadline/citation preservation regressions. Database test URL was securely
derived from `.env`; all temporary database objects were rolled back.

## Real-broker evidence and limits

`opu61-live-results.json` records UTC timestamp
`2026-10-11T04:12:56.644677+00:00`, mode
`real-kafka-real-rag-monitoring-handlers-injected-backends-no-model-calls`.

Ran `scripts/validate_resilience.py --real-rag-monitoring` inside a temporary
existing RAG image container on `opsbrain_default`, with this checkout mounted
read-only and only the validation output directory writable. The production
RAG/Monitoring FastAPI query handlers were used, but their dependencies were
explicitly injected; Code was synthetic and Infra absent for timeout testing.
This is real Kafka/handler verification, not live Groq/Gemini/backend acceptance.

All eight checks passed: poison-message recovery; mixed parallel failures retaining
success; agent recovery; eight correctly correlated simultaneous replies;
RAG dependency failure/recovery; Monitoring dependency failure/recovery;
wrong-agent rejection; pending-request release on shutdown.

Topics/groups are isolated under `opsbrain.validation.0ee2eae32c3a.`. Small test
messages remain in the retained Kafka volume. The broker was temporarily started
and restored to stopped. Operational agents were not rebuilt/restarted; apply
the query-boundary changes through the usual build/deploy workflow separately.
No model requests, ingestion, external GitHub/cluster operations or secret writes
occurred. Code remains local and uncommitted.

Groq role models, routing/synthesis, 10s/20s provider deadlines, zero provider
retries, Gemini embeddings, RAG retrieval/ingestion and HTTP default have no diff.
Only invalid output/error paths at the query boundaries were hardened. Existing
GitHub/Kubernetes setup remains deferred; no backend success is fabricated.
