# OPU-62: Infra/Code timeout and failure handling

Verified on `joint` alongside OPU-60. OPU-62 was already Done in Linear and its
implementation (`a1a806f`, Jeffin) was already integrated into this branch.
No Infra/Code production-code transplant or backend configuration was needed.

Existing behavior verified by `tests/test_agent_failures.py`:

- AWS connect/read timeouts and two maximum attempts.
- Kubernetes calls receive explicit request timeouts.
- Infra health checks execute concurrently; backend/configuration errors retain
  their non-success status instead of returning successful error prose.
- Terraform timeout/error normalization.
- GitHub HTTP failures, rate limits, connection/read timeouts and missing repo
  map to existing 503/4xx/500 responses.
- Orchestrator normalization distinguishes retryable outage from configuration
  failure, and retains successful responses.

Added `tests/test_pipeline_resilience.py` coverage invokes the real Infra/Code
FastAPI apps through AgentWorker and a serialized in-memory Kafka bus. Controlled
backend outages (503) retry exactly once; Infra config failure (500) and Code
missing resource (404) are not retried. These are injected backend failures,
not calls to live external services.

Latest full suite: **181 passed**, no skips, 37.80s, including the local pgvector
rollback test; 219 upstream warnings. Lint and both Compose configurations passed.
Real-broker transport resilience: **6/6 passed** using explicitly synthetic agent
apps; see `OPU-60.md` and `opu60-live-results.json`.

Groq models, Gemini embeddings and HTTP default remain unchanged. This does not
claim successful live access to AWS, Kubernetes or a selected GitHub repository:
those operational setup checks remain deferred. OPU-62 stays Done, with this
fresh verification added as evidence rather than duplicating its implementation.
