# OPU-88: monitoring charts and refresh controls

Implemented locally, 2026-10-11. Status: **ready for review**, pending browser QA.
Setup: [frontend README](../web/README.md).

## Delivered

- Monitoring route with synthetic CPU, memory and p95 response-latency line
  charts, percentage/millisecond scales, latest sample values and relative time.
- Accessible SVG titles/descriptions and expandable exact-value tables with
  captions and row/column headings; responsive chart and control layouts.
- Fifteen-minute and one-hour windows with four/twelve deterministic samples.
  Manual refresh alternates two fixed snapshots with a local loading state.
- Optional 30-second automatic refresh, off initially and disabled for
  Disconnected. Navigation away or hiding the tab stops it; returning does not
  automatically restart it. Refreshes do not overlap; stale completions from
  option changes or deactivation cannot overwrite the current view.
- Populated, partial, empty, error and disconnected scenarios. Partial retains
  CPU/memory while marking latency unavailable. Missing or invalid samples are
  never zero-filled. Loading/error/empty/disconnected views show no successful
  charts. Preparation errors clear old data and stop automatic refresh.
- Demo provenance, disconnected backend notice and UTC demo generation time
  explicitly distinguished from a live observation timestamp.
- Navigation/landing/dashboard copy updated, plus eight allowlisted assets
  including the monitoring module. No network calls or persistent storage.

## Verification

| Check | Result |
| --- | --- |
| `npm test` | 46 passed, no skipped or failed tests |
| `npm run check` | JavaScript syntax checks passed |
| `npm run build` | Eight allowlisted assets produced |
| `git diff --check` | Passed |

Eight added tests cover deterministic windows, availability without invented
zeroes, loading/duplicate refresh handling, stale completion cancellation,
automatic refresh scheduling/shutdown, clearing old successes on errors,
accessible charts/tables and finite coordinates, and provenance/state rendering.
Existing HTTP/build checks serve and copy the monitoring module; client checks
cover absence of network, credential and persistent-storage calls.

## Remaining acceptance

Real browser desktop/mobile, visual, keyboard and screen-reader QA remain
pending. Supported browser execution tools are unavailable in this session;
automated checks do not establish that acceptance.

No external issue-tracker status change, deployment, commit, push, backend or
environment edit. OPU-90 owns real monitoring/API integration; OPU-91 owns hosted
access controls. Next ticket in order: OPU-89, browser-local conversation history
with 72-hour expiry.
