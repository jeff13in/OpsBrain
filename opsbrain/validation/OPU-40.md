# OPU-40: local RAG validation

Validated September 4, 2026 (America/Toronto), on branch
`rifatchowdhury619/opu-40-validate-local-rag-flow-and-resolve-setup-defects`,
based on `Rifat` at `fc0f2b9`.

## Walkthrough scope

`OpsBrain_Team_Walkthrough.pdf`, pages 7, 10, and 13, assigns Week 1 to
foundation, ingestion, retrieval, containers, and shared testing/code review.
This check covers ingest → embed → store → retrieve → respond. The repository
already uses Gemini rather than the PDF's OpenAI provider and `data/` rather
than `docs/`; this validation follows that existing implementation.

## Defects resolved

1. **Fresh database initialization failed.** `database/init.sql` tried to create
   an HNSW index on `vector(3072)`. Reproducing the statement in a transaction
   returned `ERROR: column cannot have more than 2000 dimensions for hnsw index`.
   The existing database had the table but no HNSW index, so a healthy reused
   database hid the first-start failure. Removed the incompatible index;
   retrieval continues to use exact cosine distance on full-size embeddings.
   This is suitable for the local sample corpus; larger-corpus indexing needs
   a separate dimension/index design. Existing stored vectors remain usable.
2. **Quick-start expectations were stale.** The bundled corpus has two runbooks
   and six chunks, rather than the documented one document/one chunk. Corrected
   the example and added a repeatable acceptance command. Stage 1 startup now
   explicitly targets `rag-agent`, which also starts its database dependency.

## Verification results

| Check | Result |
| --- | --- |
| Rebuild/start RAG container | Passed |
| Fresh PostgreSQL instance in separate `opu40-validation` Compose project | Healthy; init script completed with `CREATE EXTENSION` and `CREATE TABLE` |
| RAG `/health` | `200`, `status: ok` |
| Live ingestion using configured Google embeddings | 2 documents, 6 chunks |
| Database inspection after each of two ingestions | Exactly 6 matching chunks, correct content and chunk indices, nonzero 3,072-dimension vectors |
| Repeat ingestion | Replaced source chunks without duplicates |
| Live CPU question | 4 retrieved chunks, `grounded: true`, no validation errors, `[runbook-high-cpu.md]` citation |
| Existing offline RAG tests | 5 passed |
| New real-database regression | Passed: fresh schema, repeated initialization, vector insert, cosine retrieval, rollback |
| Invalid API inputs | Missing ingestion directory: 404; whitespace question: 400; `top_k: 0`: 422 |

The observed answer used the existing extractive citation-validation fallback.
This validates the API's grounded response behavior; it does not establish
unrestricted generated-answer quality. No model/provider change was made.
The database regression is opt-in and reports one skip in the offline suite.
The temporary database project is removed after verification; the regular
local RAG service remains running.

Reproduce with the commands in [the setup guide](../README.md#5-validate-the-week-1-local-flow-opu-40).
The live command uses the configured Google API and replaces chunks belonging
to the input sources. The schema regression uses a transaction and leaves no
test schema or test rows behind.

## Week 1 review and remaining dependencies

GitHub's public API for `jeff13in/devops`,
`GET /repos/jeff13in/devops/pulls?state=all&per_page=100`, returned `[]` during
this validation: no open or historical PRs were available to review. The local
RAG ingestion/retrieval code, Dockerfile, Compose wiring, environment template,
database initialization, tests, and setup guide were inspected instead. This
does not substitute for the teammate PR review required on PDF page 14.

Linear dependency snapshot:

| Issue | State | Remaining closeout work |
| --- | --- | --- |
| OPU-35: project foundation | In Review | Setup PR and teammate review are still needed; no GitHub PR was found |
| OPU-36: Compose foundation | In Progress | Kafka and other planned agent stubs are absent from the current Compose file |
| OPU-37: agent containerization | Backlog | RAG startup was validated here; remaining planned agent containers are outside this fix |
| OPU-38: ingestion | Done | Live ingestion/storage validated |
| OPU-39: retrieval/API | Done | Live retrieval/response validated |

OPU-40's local RAG validation passes. Cycle 1 should not be declared closed until
the outstanding foundation dependencies and teammate PR reviews are resolved.
