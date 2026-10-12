# Rifat’s Week 4 local fixes — October 12, 2026

Linear `me` resolves to Rifat. Open assigned scope: OPU-63 and OPU-84–91.
Jeffin-assigned OPU-53/54/55/58 and their associated files remain excluded.
This pass changes the local website source, not hosted access or deployment.

## Resolved

- **OPU-89:** expiry now follows the explicit Linear requirement: 72 hours after
  the last completed message update. Reading, reopening or re-saving identical
  messages does not extend it. UI expiry dates and frontend documentation agree.
  Already expired/deleted IDs cannot resurrect old transcripts. Fake-clock tests
  check continuation across the original creation deadline and eventual expiry.
- **OPU-87/90:** live API responses retain validated routing method/reason/agent
  lists and optional per-agent latency. Chat displays both with escaped text.
  Invalid/mismatched routing and negative/excessive latency are rejected. Older
  demo fixtures without these fields remain valid; no metadata is fabricated.
- **OPU-90:** a late live answer is rejected when connection/session generation
  changed, even if the injected transport ignores AbortSignal. Existing chat
  cancellation and deliberate demo/live switching remain intact.

## Verification

- Frontend full suite: **122 passed**, no skips/failures (4.34s), including real
  loopback gateway/server tests with controlled backend responses.
- JavaScript checks and build pass; 14 allowlisted assets.
- Public credential-pattern scan: **0 findings**.
- No Python runtime, Terraform, deployment-manifest, CI or provider changes in
  this pass. Existing observability work from the earlier pass is preserved.

## Remaining assigned work

| Tickets | Remaining acceptance |
| --- | --- |
| OPU-84/85/86 | Real browser responsive/keyboard/visual acceptance; current component tests/build pass |
| OPU-87/88/89 | Real browser interaction/accessibility acceptance; local rendering, chart refresh, storage and unsafe-content tests pass |
| OPU-90 | Configured real OpsBrain and protected hosted API connectivity; local adapter/gateway cases pass |
| OPU-91 | Second approved email, hosted enforcement/denied-user checks, approved protected API origin and hosted browser/deploy/rollback evidence |
| OPU-63 | Review of deployed acceptance and hosted evidence from prerequisite OPU-57/91; cannot sign off based on local unit/syntax results |

Browser-control tools are not callable in this session. No substitute browser
or invented visual acceptance is used. The user explicitly deferred hosted setup; [OPU-105](https://linear.app/opusbrain/issue/OPU-105/week-4-hosted-preview-access-and-protected-api-acceptance-deferred)
preserves second-viewer identity, host enforcement, protected API, hosted browser
acceptance and deployment/rollback work. No identity, credentials or hosted access
were guessed. No invitation, publication, deployment, commit or push occurred.
Tickets stay open for their remaining acceptance, with completion notes for
these verified fixes. Local changes are uncommitted.
