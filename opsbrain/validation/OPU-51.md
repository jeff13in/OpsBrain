# OPU-51: full async multi-agent pipeline run

Validated October 10, 2026, on branch
`ejffinsam14/opu-51-run-full-async-multi-agent-pipeline-and-fix-integration`,
based on `jeffin-dev` at `dde55d7` (OPU-50 merged). Full stack via
`docker compose --profile full up --build -d` on Docker 29.5.3, with
`AGENT_TRANSPORT=kafka` on every service.

## Environment

| Setting | Value |
| --- | --- |
| `GOOGLE_API_KEY` | Set (free tier: 5 requests/min for `gemini-3.6-flash`) |
| `POSTGRES_PASSWORD` | Set; runbooks ingested (2 documents, 6 chunks) |
| `GITHUB_TOKEN` / `GITHUB_REPO` | **Not set**, so the Code agent answers with its "not configured" 500 |
| AWS credentials / `KUBECONFIG` | **Not set**, so the Infra agent answers with its "no config" 500 |

Infra and Code therefore exercised the failure path end to end. Their success
path over Kafka is covered by unit tests and the same worker code that
RAG and Monitoring ran successfully here, but not with real AWS/GitHub data.

## Defects found and fixed

1. **A rate-limited Gemini key stalled `/ask` for over a minute.** Asking "hi"
   took 67s even though RAG rejected it in 30ms. The orchestrator's Gemini
   client retried 429 `ResourceExhausted` (free tier, 5 requests/min) up to 6
   times with backoff, with no overall time limit, so the keyword fallback never
   started. Fix: `max_retries=1`, and hard per-call limits of 10s for routing
   and 20s for synthesis (`ORCHESTRATOR_ROUTE_TIMEOUT_SECONDS`,
   `ORCHESTRATOR_SYNTH_TIMEOUT_SECONDS`). After the fix, rate-limited requests
   fall back to keyword routing in 0.1–0.2s.
2. **Monitoring answered only one topic per question.** "Which alerts are firing,
   are any pods crashlooping…" returned only pod health, because `ask()` used
   the first keyword match. It now answers every topic mentioned (alerts, pods,
   scrape targets), keys `data` by topic, and reports a failed backend in the
   answer if at least one other topic succeeded (503 only if all fail).
3. **Service logs hid the Kafka layer.** uvicorn configures only its own
   loggers, so INFO lines like "listening on …" and "Skipping request …" were
   dropped. Without them, a stale request couldn't be confirmed as skipped
   rather than answered. Fix: `shared.agent_bus.configure_logging()` turns on
   INFO for the `shared` and `orchestrator` loggers only, so kafka-python stays quiet.

## Verification results

| Check | Result |
| --- | --- |
| All images build with `shared/`, `kafka-python`, `httpx` | Passed |
| Services wait for the Kafka healthcheck | Passed: agents and orchestrator start after `kafka` is healthy |
| Topics auto-created | `opsbrain.agent.{rag,monitoring,infra,code}.requests`, `opsbrain.agent.replies` |
| Consumer groups | `rag-agent`, `monitoring-agent`, `infra-agent`, `code-agent`, `orchestrator-<id>`, one partition each |
| One question routed to all four agents (Gemini) | `partial`, HTTP 200 in 28.8s: RAG ok (17.2s), Monitoring ok with alerts + pods, Infra and Code `agent_error` (no credentials); merged answer cites both successful agents |
| RAG-only question | `ok`, answer cites `runbook-db-connections.md` |
| Monitoring-only (alerts, scrape targets) | `ok`, 1.2–1.5s end to end, agent time 20–44ms |
| Follow-up in same session ("and which of those matter most?") | Rewritten with history, routed to RAG + Monitoring |
| Agent down (container stopped) | `timeout` at 30.0s, `status: error`, HTTP 502 |
| Agent restarted with a stale request in its topic | Consumed (lag 0) and logged `Skipping request …: the Orchestrator already timed out`; no stale reply |
| 6 questions in a row (past Gemini's 5/min) | Requests 1–3 `llm` routing (1.7–2.4s); 4–6 `keyword` fallback (0.1–0.2s), all HTTP 200 |
| 8 concurrent `/ask` requests | All 8 correct, done in 4s total, no crossed replies |
| `pytest` / `ruff check .` | 89 passed, 1 skipped / clean |

## Known gaps, not fixed here

- **Questions under 5 characters fail.** "hi" goes to RAG, whose `/query`
  requires at least 5 characters, so it returns 422 → `bad_request` →
  HTTP 502. This is `CONTRACT.md` known gap 3. The fix belongs in the RAG agent
  (Rifat's code) or in routing.
- **Infra and Code not run against real AWS, Kubernetes or GitHub** (no credentials
  in this environment).
- **Agents have no `/metrics` endpoint**, so Prometheus reports 5 of 7 scrape
  targets as down (the five OpsBrain services). Monitoring reports this correctly.
- **The Gemini free tier allows 5 requests/min**, and every `/ask` uses 1–2 of
  them (routing, plus synthesis when two or more agents answer). Under real use,
  most requests will route by keyword unless the key is upgraded.
