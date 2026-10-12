# OPU-89: browser-local conversation history

Implemented locally, 2026-10-11. Status: **ready for review**, pending browser QA.
Setup: [frontend README](../web/README.md).

## Delivered

- Completed demo conversations save automatically to one versioned browser
  storage key, retaining questions, answers, citations and per-agent outcomes.
- History lists saved conversations, UTC creation/expiry dates and turn counts.
  Open in chat restores a conversation for continuation. New conversation
  resets active chat while retaining its saved record. Individual/bulk deletion
  clears affected active chat and invalidates pending completions.
- Absolute 72-hour expiry measured from creation; continuing or opening does
  not extend it. Expired records are rejected on access and removed during
  visible-page minute checks, navigation and visibility/storage events.
- Bounded retention of the latest 20 conversations and 20 turns per conversation.
  Pending turns are excluded. Reload recovery retains Demo provenance.
- Defensive storage schema, field/count/size limits, future-date rejection,
  duplicate-ID filtering and escaped stored text. Unknown fields are excluded
  when saving. No external links or stored HTML are executed.
- Storage denial/quota errors preserve history in page memory and show that
  persistent writes/deletions may not have succeeded. Other storage keys are
  untouched; reads observe other tabs' existing records before writes.
- History route/navigation and chat/landing descriptions updated. Nine explicit
  public assets include the history module; no backend calls or environment edits.

## Verification

| Check | Result |
| --- | --- |
| `npm test` | 54 passed, no skipped or failed tests |
| `npm run check` | JavaScript syntax checks passed |
| `npm run build` | Nine allowlisted assets produced |
| `git diff --check` | Passed |

Eight new tests cover reload recovery, exact expiry boundary without extension,
deletion isolation, retention bounds and pending-turn exclusion, storage failures,
invalid/oversized history, escaped restored results, cancellation on restore,
and sequential multi-store reads/deletes. Existing HTTP/build tests include the
history module. Client checks isolate browser storage access to that module and
continue to exclude network and credential calls.

## Remaining acceptance and limits

Actual browser desktop/mobile, visual, keyboard and screen-reader QA remain
pending; no supported browser execution tool is available in this session.
Automated checks do not establish browser-storage or visual acceptance.

Storage is specific to browser profile and origin, with no account protection,
encryption or server sync. Physical expiry cleanup requires a running website.
Concurrent writes in separate tabs are best effort, not transactional. Failed
storage writes/deletes can leave previously persisted disk data, as the UI warns.

No external tracker status change, deployment, commit or push. Next: OPU-90,
read-only API adapter and deliberate demo/live transitions.


## Rifat’s assigned-scope follow-up — October 12, 2026

See [local fixes and current acceptance](week4-rifat.md): history retention now
uses last-message updates per OPU-89; API/chat preserve safe routing/latency;
late answers cannot survive session/connection changes. All 122 frontend tests,
syntax/build checks and the public credential-pattern scan pass. Prior
implementation/results above are historical; browser/hosted gates remain open.
