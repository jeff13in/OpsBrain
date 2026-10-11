# OPU-83 acceptance: passed

Verified October 10, 2026 (America/Toronto; live JSON timestamp October 11 UTC).

The synthesis implementation was already delivered with the model migration;
no additional production-code changes were needed for this acceptance check.
Existing unrelated worktree changes were preserved.

## Implementation

- `orchestrator/main.py` resolves `get_llm("synth")` independently of the router;
  `orchestrator/llm.py` delegates this to shared `get_chat_model("synth")`.
- The configured default synthesis model is `qwen/qwen3.8-27b` on Groq.
- Synthesis retains its 20-second wall-clock deadline and disables SDK retries.
- Successful merging preserves source citations and appends any missing source
  references and unavailable-agent names/error codes.
- On HTTP 429, timeout, other provider failure or empty output, the graph uses
  the existing `fallback_answer()` with labelled agent sections, sources and
  unavailable-agent reporting. Partial workflow status is preserved.

## Fresh verification

From `opsbrain/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_llm_migration.py tests/test_orchestrator_graph.py tests/test_agent_bus.py -q
.\.venv\Scripts\python.exe -m scripts.validate_transport --transport http --output validation/opu83-live-results.json
```

- Regression tests: **72 passed**, 27.78 seconds, 219 upstream deprecation
  warnings. Tests cover independent synthesis-role selection, successful source
  preservation and unavailable-agent reporting, real SDK/mocked HTTP 429 with
  exactly one request, cancelled timeout calls and labelled-section fallback.
  Failure injection is deterministic/mocked; no provider quota was deliberately
  exhausted. The timeout test shortens the wait and asserts the production
  deadline remains 20 seconds.
- Live local-service/provider smoke: **7/7 passed**. Five metrics endpoints and
  two deployed `/ask` calls passed. Real RAG + monitoring answers were merged
  rather than returned as fallback sections, with every source citation present;
  combined request completed in **4.578 seconds**. See `opu83-live-results.json`.
- Existing `integration-full-results.json` also records real Qwen synthesis
  retaining citations and explicitly listing unavailable infra/code agents in
  a partial four-agent workflow. Those backend setup failures remain deferred;
  they are not relabelled as successful backend checks.

The existing prior full regression run was **124 passed**, no skips; prior live
HTTP and Kafka smoke runs each passed **7/7** (`agent-integration.md`). This turn
did not change transport settings, embeddings, ingestion or model routing.
