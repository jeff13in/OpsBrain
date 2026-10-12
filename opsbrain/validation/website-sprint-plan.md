# Website sprint review and follow-up plan

Reviewed 2026-10-11 against the current `web/` implementation and the backend
routes it uses; reconciled with the actual Linear roadmap on 2026-10-12 during OPU-92.
OPU-92–98 now identify the seven Week 5 authentication/workspace issues.
The former draft OPU-92–94 live-data deliverables below remain preserved as
named follow-ups with issue IDs unassigned; they are not those Linear tickets.

## Review of the existing website sprints

| Sprint | Current result | Follow-up needed |
| --- | --- | --- |
| OPU-84 — foundation and visual design | Implemented locally; reusable UI, responsive navigation and safe static build are present. | Complete real-browser desktop/mobile, keyboard, focus, contrast and screen-reader acceptance in OPU-91. |
| OPU-85 — landing page | Implemented locally with accurate product and access-limit copy. | Recheck links, responsive layout and public-facing wording on the hosted origin in OPU-91. |
| OPU-86 — dashboard demo | Implemented locally with labelled synthetic states. | Replace the sparse live dashboard with truthful API status in Live-readiness follow-up; demo fixtures remain available. |
| OPU-87 — demo chat | Implemented locally with citations, partial failures and escaped output. | Run browser acceptance in OPU-91. Preserve partial results and provenance in later live changes. |
| OPU-88 — demo monitoring | Implemented locally with fixed charts and accessible value tables. | Add bounded live time-series data in Live-timeseries follow-up; synthetic charts must stay clearly labelled. |
| OPU-89 — browser-local history | Implemented locally with expiry, validation and deletion. | Keep it demo-only until authenticated, account-scoped storage is delivered in Live-history follow-up. |
| OPU-90 — local live API adapter | Implemented locally through an allowlisted localhost gateway. | Verify it against the real backend in OPU-91; production traffic requires protected same-origin routing. |
| OPU-91 — hosted private preview | Planned and still the release gate. | Refine it with the acceptance criteria below before starting later live-data work. |

The sequence remains intentionally incremental: OPU-91 establishes a private,
testable deployment. Week 5 adds client identity/workspaces; the preserved live
readiness and time-series follow-ups add truthful operational data. Account-scoped
live history also requires the separate client-data isolation gate.

## OPU-91 — private hosted preview and acceptance gate

**Goal:** make the existing website safely reviewable by the two approved
engineers on a stable URL, with a protected API path and repeatable frontend CI.

Scope:

- Deploy the static frontend and a same-origin gateway on a free or already
  approved hosting tier. Do not ship the localhost development gateway as the
  production security boundary.
- Require sign-in and allow exactly the two approved email identities. Deny an
  unauthenticated visitor and an authenticated but unapproved identity.
- Protect the browser, gateway and upstream API independently. Keep agents and
  monitoring services off the public internet.
- Add frontend test, syntax and build jobs to pull requests and the active
  collaboration branch. Configure production CSP and the security headers that
  currently exist only in the local preview server.
- Run the existing chat and monitoring adapter against the configured backend,
  including success, partial-agent failure, total failure, timeout and malformed
  response behavior. Verify that demo data is never used as a live fallback.
- Complete desktop and mobile visual checks, keyboard-only navigation, visible
  focus, browser storage behavior, reduced motion, and a screen-reader smoke test
  for Home, Overview, Chat, Monitoring and History.

Acceptance criteria:

1. Only the two allowlisted identities can load the site; direct API requests
   without valid access are rejected and no secret is present in built assets.
2. A pull request cannot pass the frontend gate when tests, syntax checks or the
   allowlisted static build fail.
3. Hosted Chat returns a real contract-compatible response and preserves sources
   and per-agent failures. Hosted Monitoring reports snapshot failures honestly.
4. Refreshing every hash route works on the hosted origin, and the browser
   console has no uncaught errors during the acceptance path.
5. The browser/accessibility checklist is recorded with viewport, browser and
   result evidence. Any exception becomes a named follow-up rather than a blanket
   claim of accessibility.
6. The deployment and rollback steps, public origin, identity owner and gateway
   owner are documented without committing credentials.

Out of scope: public signup, write-capable operational actions, real monitoring
charts, server-side conversation history and production availability claims.

## Live-readiness follow-up — live dashboard and service readiness

**Goal:** make Overview useful in live mode without presenting a successful
orchestrator health check as proof that every dependency is healthy.

Scope:

- Define a bounded status contract for the Orchestrator and four specialist
  agents. Distinguish gateway reachability, service readiness, configured
  dependencies and unknown/unavailable state.
- Add an authenticated, read-only aggregate status endpoint through the
  same-origin gateway. Use short deadlines and return partial results when one
  service cannot answer.
- Render last retrieval time, per-service state and safe diagnostic summaries on
  Overview. Provide manual refresh and an optional paused-by-default interval;
  stop background refresh when the page is hidden.
- Keep stale results visibly stale and never turn missing data into a healthy
  state. Do not expose credentials, internal exception text or unrestricted
  upstream URLs.

Acceptance criteria:

1. Tests cover all-ready, partial, unavailable, timeout, malformed and stale
   responses, including cancellation after navigation or mode changes.
2. The UI identifies retrieval time separately from the time a dependency was
   observed, and every state has a text label in addition to color.
3. An Orchestrator-only success cannot produce an all-systems-healthy display.
4. Hosted browser verification confirms responsive layout, keyboard operation
   and no demo/live provenance confusion.

Depends on OPU-91. Out of scope: alert mutation, restart/deploy controls and
arbitrary health targets supplied by the browser.

## Live-timeseries follow-up — live monitoring time-series

**Goal:** replace the live page's snapshot-only view with real CPU, memory and
latency charts while retaining partial availability and accessible tables.

Scope:

- Add server-owned, allowlisted metric presets for the three existing chart
  types and the existing 15-minute/hour ranges. The browser may select a preset
  and range; it may not submit arbitrary PromQL or an upstream address.
- Normalize bounded samples, timestamps, units and missing values at the API
  boundary. Cap range, step, series count and response size.
- Reuse the chart and exact-value table presentation, replacing Demo provenance
  with Live only after a validated response. Preserve successful series when a
  different metric fails.
- Add manual refresh and a user-controlled interval that pauses while hidden,
  suppresses overlapping requests and marks retained results stale after errors.

Acceptance criteria:

1. Contract and gateway tests reject unknown presets, excessive ranges,
   malformed samples, redirects and oversized responses.
2. A real configured monitoring backend supplies at least one recorded hosted
   acceptance run; absence of a metric is shown as unavailable, never zero.
3. Chart labels, units, time zones, table values and partial failures agree, and
   keyboard/screen-reader users can inspect the same values.
4. Demo mode remains deterministic and visually distinct from Live mode.

Depends on OPU-91; use the Live-readiness follow-up status contract where useful. Out of scope:
arbitrary query consoles, dashboard editing, alert acknowledgement and long-term
analytics storage.

## Live-history follow-up — authenticated conversation history

**Goal:** let an approved engineer resume live investigations across browser
sessions without mixing identities or weakening the current retention limits.

Scope:

- Store live conversations behind the authenticated API, scoped to the verified
  identity. Generate record ownership on the server and never trust an email or
  owner identifier supplied by the browser.
- Provide bounded list, read, create/update and delete operations with schema
  validation, pagination and idempotent writes. Retain sources, per-agent status
  and timestamps needed to reproduce the displayed conversation.
- Define and enforce a short retention period before collecting live questions;
  expose expiry and deletion behavior in the UI. Record access/deletion events
  without logging question or answer bodies.
- Keep current browser-local Demo history separate. Clearly label Demo and Live
  records and provide an explicit empty/error state when server history is
  unavailable.

Acceptance criteria:

1. Cross-user read, update and delete attempts fail in API tests and in a hosted
   two-identity acceptance check.
2. Expiry, pagination, duplicate retries, concurrent updates and deletion are
   covered without exposing one identity's content to the other.
3. Stored and restored content remains escaped plain text, preserves provenance
   and obeys the same field/count/size bounds as new responses.
4. The retention decision, storage location, backup implications and deletion
   limitations are documented before the feature is enabled.

Depends on OPU-91. Out of scope: team sharing, exports, indefinite retention,
full-text search and storing provider credentials or hidden model context.

## Week 5 — authentication and client workspace

The user inserted this week without changing Week 4. Actual OPU issues:

| Issue | Work package | Priority | Dependencies |
| --- | --- | --- | --- |
| OPU-92 | Architecture & Project Audit | Urgent | Audit Week 4 prerequisites |
| OPU-93 | Supabase Infrastructure Setup | Urgent | OPU-92 |
| OPU-94 | Homepage Login & Signup | High | OPU-93 |
| OPU-95 | Authentication Routing & Session Management | Urgent | OPU-93, OPU-94 |
| OPU-96 | Client Workspace UI | High | OPU-95 |
| OPU-97 | Workspace Data & Persistence | High | OPU-93, OPU-95, OPU-96 |
| OPU-98 | Security, QA & Deployment Readiness | Urgent | OPU-92–97 |

Architecture and verified source boundaries are in
[the client workspace contract](../architecture/client-workspace.md).
The first release is an approved-client beta. Saved client work is retained
until the client deletes it; browser-local demo history keeps its existing
72-hour behavior. Shared live integrations require explicit tenant isolation
before becoming available to clients. Team collaboration, billing and uploads
are later scope.

## Week 6 — existing regression work preserved

Linear's former Week 5: Regression Testing milestone is now Week 6: Regression
Testing. All 15 existing issues, deliverables, owners, priorities and dependency
relationships remain. A fresh Linear check on October 12, 2026 shows its current
target is October 23, 2026; the earlier October 16 target has been superseded.
No Week 7 or later milestone was found, so no missing work was invented.

Linear now lists October 16, 2026 as Week 5's target and October 23 as Week 6's
target. Week 5's milestone description still says calendar dates are unset;
the structured target is recorded here without treating it as agreed capacity.
Week 4 is incomplete, and the project's historical October 7 target precedes
both remaining milestone targets. Capacity,
prerequisites and the actual delivery calendar must be reviewed before promising
completion. Week labels express order, not an agreed current start date.

## Preserved operational follow-up order

1. Finish OPU-91 and record the hosted/browser acceptance evidence.
2. Deliver Live-readiness follow-up so the live workspace reports useful, honest status.
3. Deliver Live-timeseries follow-up using the protected gateway and status conventions.
4. Deliver Live-history follow-up only after authentication identity is stable and the retention
   decision has an owner.

Live-readiness follow-up and Live-timeseries follow-up may be designed together, but they should remain separate
review units: status/readiness and time-series queries have different contracts,
failure modes and security limits.
