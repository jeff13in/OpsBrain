# OpsBrain

This legacy filename is retained for existing IDE bookmarks. The maintained
overview is [README.md](README.md); commands and agent endpoints are in the
[operations guide](opsbrain/README.md).

The shared development branch is `joint`. Chat roles use Groq; Gemini remains
the RAG embedding provider. HTTP is the Compose default; Kafka is opt-in.
OPU-52 documentation changes do not alter API, model or transport settings.

- [Async architecture and agent integration points](opsbrain/architecture/async-integration.md)
- [Orchestrator request/response contract](opsbrain/orchestrator/CONTRACT.md)
- [Cycle 3 review, evidence and Week 4 limitations](opsbrain/validation/OPU-52.md)

The review distinguishes tested local integrations from deferred real
GitHub/AWS/Kubernetes acceptance. Read the handoff before treating deployment
templates or historical PR descriptions as production-ready.
