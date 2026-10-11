# OPU-86: dashboard demo fixtures and states

Implemented locally, 2026-10-11. Setup: [frontend README](../web/README.md).

## Delivered

- Immutable synthetic fixtures for four agents, scalar operational signals and
  example activity, served as an explicit allowlisted static module.
- Dashboard selector and direct URL states for populated, partial availability,
  loading, empty, error and disconnected previews. Missing or invalid states
  default to disconnected.
- Backend connectivity remains visibly disconnected in every state. Sample cards,
  signals and activity use Demo labels; no sample readiness implies live health.
- Partial availability marks Code unavailable and excludes its example activity
  while preserving the other sample context. Loading, empty, error and disconnected
  previews contain no successful metrics or activity. Error reset changes only
  the demo state.
- Visible selector label, state announcements and focus restoration after state
  changes; responsive card, signal and control layouts.
- Landing scope updated to reflect the available dashboard demo. Investigation
  links retain ticket-labelled placeholders for chat, charts and history.

## Verification

| Check | Result |
| --- | --- |
| `npm test` | 29 passed, no skipped or failed tests |
| `npm run check` | JavaScript syntax checks passed |
| `npm run build` | Six allowlisted assets produced |
| `git diff --check` | Passed |

Seven new tests cover safe state parsing, fixture immutability, provenance in
every state, deterministic sample rendering, preservation of partial results,
absence of successful metrics in unavailable states and escaping dynamic card
text. HTTP tests include the demo module, build tests verify allowlisted output,
and client checks cover the absence of network, credential and storage calls.
The loopback HTTP suite required running outside the filesystem/network sandbox
because its first attempt could not bind localhost (`EPERM`). The rerun passed.

## Remaining review and scope

Real browser desktop/mobile, visual and keyboard QA remain pending: no supported
browser execution tool was available in this session. Automated checks do not
establish visual or assistive-technology acceptance.

No backend, environment, provider, database or hosting changes. No deployment,
commit or push. Demo preview states never become fallback data for a live API.
OPU-87 (chat, citations and per-agent results) is next, followed by OPU-88 through
OPU-91 in the frontend README's agreed order.
