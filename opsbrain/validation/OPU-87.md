# OPU-87: demo chat, citations and per-agent results

Implemented locally, 2026-10-11. Status: **ready for review**, pending browser QA.
Setup: [frontend README](../web/README.md).

## Delivered

- Functional demo chat route with labelled question input, length validation,
  explicit response-scenario selection, loading and duplicate-submit prevention.
- Fixed synthetic success, partial and all-failed responses. Every response is
  labelled Demo and the interface discloses that its answer is independent of
  the submitted question. No model, backend or operational query occurs.
- Numbered citations focus matching synthetic source entries. Expandable
  per-agent results keep agent identity, outcome, answer/source text or failure
  reason visible. Partial replies retain successful context; failed agents
  contribute no sources. All-failed responses provide no diagnosis or sources.
- Escaped plain-text questions, answers, sources and error messages. No HTML or
  Markdown rendering and no external source links. Unknown citation numbers
  remain plain text instead of becoming invented source references.
- Page-memory conversations bounded to 20 turns, retained across route navigation.
  Clearing resets the conversation and ignores any stale pending completion;
  reload removes page memory. No persistent history or backend session yet.
- Accessible form labels, status announcements, completion focus and responsive
  composer/result layouts. Landing/dashboard copy reflects the demo chat.
- Seven explicit static assets including the new chat module. Existing localhost
  restrictions, CSP and backend/credential-file exclusion remain enforced.

The demo uses the backend's `status`, `answer`, `sources` and `results` names.
OPU-90 still owns response validation and connection to the actual `/ask` API.

## Verification

| Check | Result |
| --- | --- |
| `npm test` | 38 passed, no skipped or failed tests |
| `npm run check` | JavaScript syntax checks passed |
| `npm run build` | Seven allowlisted assets produced |
| `git diff --check` | Passed |

Nine new tests cover input limits, duplicate submissions, ordered turns, clearing
and stale response handling, bounded page memory, safe preparation errors,
partial/all-failed outcomes, text escaping, source-target consistency, and
empty/loading markup. Existing HTTP/build tests include the chat module, and
client checks verify absence of network, credentials and persistent storage.

## Remaining acceptance

Actual browser desktop/mobile, visual, keyboard and screen-reader review remain
pending. A supported browser execution tool was unavailable in this session;
automated checks do not establish that acceptance.

No external tracker status was changed. No deployment, commit, push, backend or
environment changes. Next ticket: OPU-88, monitoring charts and refresh controls.


## Rifat’s assigned-scope follow-up — October 12, 2026

See [local fixes and current acceptance](week4-rifat.md): history retention now
uses last-message updates per OPU-89; API/chat preserve safe routing/latency;
late answers cannot survive session/connection changes. All 122 frontend tests,
syntax/build checks and the public credential-pattern scan pass. Prior
implementation/results above are historical; browser/hosted gates remain open.
