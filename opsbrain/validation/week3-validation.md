# Week 3 validation — October 12, 2026

The user requested completion of outstanding Week 3 work. The user subsequently requested separate Week 3 tickets for unavailable live
setup/acceptance and fixes for other issues. OPU-51 and OPU-52 are closed for
verified implementation/review scope; their live gate is preserved in OPU-100–103.
Implementation tickets OPU-47–50 and OPU-60–62 are Done.

## Completed local work

- Added `tests/test_week3_integration.py`: the actual `/ask` endpoint and
  LangGraph dispatch through `KafkaAgentBus` and `AgentWorker` to all four actual
  RAG, Monitoring, Infra and Code `/query` apps. The in-memory broker invokes
  the production serializers/envelope models. External backends are controlled:
  runbook retrieval and Alertmanager/GitHub responses are fixtures, AWS is moto.
- Verified successful four-agent aggregation, ordered outcomes/sources, actual
  EC2 and commit normalization, matching request/reply correlations, conversation
  memory, four concurrent requests without crossed replies, and a Code 503
  that retries once and preserves the other three successful answers.
- Found and fixed a real routing defect: `procedure` supplied the substring
  `pr` and `EC2` supplied the digit 2, so the Code Agent interpreted a commits
  question as PR #2. Numeric lookup now requires an explicit PR/pull-request
  marker or `#number`. The successful all-four and concurrent cases reproduce
  the failing question and prevent its recurrence.
- Extended `scripts/validate_transport.py` with `--all-agents` for repeatable
  live all-four acceptance once external setup is available. Existing default
  RAG/Monitoring smoke checks are preserved. CLI help and lint pass; no live
  result is invented by this extension.
- Re-reviewed the async transport and graph against `OPU-52.md`: correlation,
  serialization validation, retry/deadline and partial-answer behavior retain
  their coverage. Queue bounds, consumer recovery/delivery semantics, backend
  redaction, deployment authorization and replica memory remain documented
  operating follow-ups. Architecture is in `architecture/async-integration.md`.

## Fresh results

| Check | Result |
| --- | --- |
| Python 3.12.9, `python -m pytest tests -q` | **297 passed, 1 skipped**, 38 subtests passed; 24.55 seconds |
| New four-agent Kafka integration cases | **3 passed** within the full run |
| Ruff for agents/orchestrator/shared/scripts and new integration test | Passed |
| `python -m scripts.validate_transport --help` | Passed; `--all-agents` documented |
| `git diff --check` | Passed |

The skip requires `RAG_TEST_DATABASE_URL`. This fresh verification uses an
in-memory broker and controlled backends; it is not real Kafka/provider/AWS/
Kubernetes/GitHub success acceptance. Historical real-broker evidence remains
in `OPU-51.md`, `OPU-60.md`, `OPU-61.md` and the recorded integration JSON files.

## Outstanding live acceptance

This machine has no Docker executable at the standard PATH/app locations, no
project `.env`, no default kubeconfig, and no process configuration for GitHub,
model keys or Kafka. AWS credential/config files exist; their values were not
printed and no AWS account/access claim is made. These files alone do not supply
the missing broker, Kubernetes and provider setup.

The user's subsequent instruction was: “Create some sprints on week 3 to have
those issues logged and fix any other issues that is not related to them.”
The unavailable setup and live acceptance are now explicit Backlog tickets in
the same Week 3 milestone, preserving their original requirements:

| Ticket | Remaining work |
| --- | --- |
| [OPU-100](https://linear.app/opusbrain/issue/OPU-100/31-configure-live-kafka-model-providers-and-rag-data) | Real Kafka/Docker stack, model keys, pgvector and runbooks |
| [OPU-101](https://linear.app/opusbrain/issue/OPU-101/32-configure-and-validate-the-selected-github-repository) | Selected repository/token and real GitHub read acceptance |
| [OPU-102](https://linear.app/opusbrain/issue/OPU-102/33-configure-and-validate-real-aws-and-kubernetes-access) | Approved AWS and reachable Kubernetes backend acceptance |
| [OPU-103](https://linear.app/opusbrain/issue/OPU-103/34-run-live-all-four-agent-kafka-acceptance-and-close-review) | Full live pipeline/recovery/shared review; blocked by all three setup tickets |

OPU-51/52 Done covers the verified implementation and documentation. **Week 3
overall is still open** because the four follow-ups remain Backlog. Real-backend
acceptance has not been claimed or discarded.

Once the chosen repository/token, AWS/Kubernetes access, model keys and local
stack are configured, run from `opsbrain/`:

```bash
docker compose -f docker-compose.yml -f docker-compose.kafka.yml --profile full up --build -d
# Add docker-compose.kubernetes.yml with KUBECONFIG_HOST for host kubeconfig access.
python -m scripts.validate_transport --transport kafka --all-agents --output validation/week3-live-results.json
```

The validator requires successful statuses for all four agents and model routing/
synthesis, not a partial answer caused by absent configuration. Configure/ingest
the actual runbooks first as documented in the README; this command does not
manufacture backend setup or prove Kubernetes-specific success from an EC2-only
query. Record additional direct Kubernetes checks for the selected cluster.

## Legacy plan

The older Week 3 backlog overlaps implemented active work: TES-16 maps to
OPU-47/50 (Kafka), TES-18 to OPU-48/49/62 (Infra/Code), and TES-14 to OPU-45
(CI; the existing GHCR migration supersedes ECR). Those implementation scopes
are closed with cross-links and explicit evidence boundaries. Canceled legacy
proposals retain their states. Live acceptance is now preserved explicitly in OPU-100–103.

Runtime fix, new tests and validation documentation remain local/uncommitted.
No deploy, workflow trigger, commit, push or image publication occurred.


## Independent defects resolved — OPU-104

- Kafka worker admissions are bounded to four running plus 32 queued requests
  by default. Valid unexpired overload receives 503 without backend work;
  malformed, misrouted and expired overload is dropped. Completion/cancellation
  releases slots. Tests cover rejection and successful re-admission.
- Worker and orchestrator reply listeners reconnect after post-startup failures.
  Old connections close; reply readiness clears and pending callers fail before
  recovery. Tests verify successful post-recovery round trips on both sides and
  that exception payloads are omitted from logs.
- Infra/Code query and typed endpoints retain 400/404/500/503 status categories
  with generic errors. Raw upstream messages/URLs are omitted from responses
  and logs; successful partial Infra health data also redacts backend failures.
  Tests include secret-bearing errors across all status categories.

[OPU-104](https://linear.app/opusbrain/issue/OPU-104/35-fix-kafka-overloadrecovery-and-redact-backend-failures)
is Done for those local fixes. Final regression: **309 passed, 1 skipped**,
38 subtests passed, 24.56 seconds. Relevant production/script/new-test lint and
`git diff --check` pass. Twelve new hardening cases pass in the full run.
The earlier 297-test table is retained as the first validation snapshot.

Auto-commit/crash delivery remains best-effort, with no exactly-once guarantee.
Caller timeouts still do not forcibly cancel synchronous backend work. Replica
memory, broker/agent authorization and actual deployment are Week 4 operating
limits; these fixes do not certify production readiness.
