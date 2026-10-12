# OPU-96 client workspace UI

Local implementation, October 12, 2026. Free-only budget preserved. The client
shell requires OPU-95 session authorization and an authorized workspace summary;
an absent backend provides loading/error views rather than fabricated client data.

OPU-97 supersedes the initial read-only availability below: when migration 003
and its APIs are present, Projects and Settings enable validated writes and saved
demo investigations. Live tools and the complete activity feed remain disabled.
See [current persistence contract](workspace-persistence.md).

## Routes and availability

| Hash route suffix under #/workspace/ | Behavior |
| --- | --- |
| dashboard | Authorized workspace name, profile welcome, recent projects and availability |
| tools | Demo tool entry points; live integrations explicitly unavailable |
| projects | Paginated project CRUD, explicit Demo saves and saved-investigation reopen/delete when persistence is available |
| activity | Actual recent project-update timestamps; complete activity feed unavailable |
| settings | Authorized display name/workspace and validated profile/start-page/motion preferences |
| help | Built-in beta, demo, retention and support explanations |
| demo-chat | Existing fixed-response chat, citations and per-agent results |
| demo-monitoring | Existing synthetic charts/tables, refresh and scenario controls |
| demo-history | Existing browser-local history, restore/delete/filter and 72-hour expiry |

Unknown suffixes resolve to Dashboard. Client navigation has one current-page
label, and demo subroutes activate Software tools. Existing public engineer/demo
routes remain separate. Entering the client shell disconnects engineer live mode;
client tool pages have no live connection controls. Browser demo history is clearly
labelled and remains independent of account records, including across account
switches on the same browser. No shared operational data is made client-accessible.

The account menu uses native details/summary and links to settings/help plus the
existing server logout action. Existing mobile Menu/skip link/focus behavior is
reused. Added responsive single-column layouts and bounded text wrapping.
Real mobile/desktop visual and assistive-technology acceptance remains open.

## Read-only summary contract

GET `/api/workspaces/{uuid}/summary` requires the opaque server session. Backend
authentication revalidates identity/workspaces; an unauthorized workspace gets
404, absent identity 401 and provider/store failure a safe 503. Successful data
is Cache-Control: no-store. The selected workspace must be in the verified
membership list; every ordinary read uses a publishable key plus user Bearer
token under the existing RLS policies. Privileged session-store credentials never
serve application data reads.

The provider reads workspace id/name, the verified user's profile display name,
and at most ten projects filtered to that workspace, ordered by update time and
id. It validates matching workspace/user IDs, bounded text, timestamps and
versions. The frontend validates the contract independently and copies only
allowed fields. There is no server/client HTML, provider token or arbitrary target
URL in the response. Example shape (illustrative IDs/data only):

```json
{
  "workspace": {"id": "00000000-0000-4000-8000-000000000002", "name": "Personal workspace"},
  "profile": {"display_name": ""},
  "recent_projects": [],
  "capabilities": {"project_writes": false, "preferences": false, "activity": false, "live_tools": false}
}
```

Recent project rows include id, title, updated_at (timezone-aware ISO timestamp)
and positive safe-integer version. The controller accepts at most ten unique
rows and a 16,384-character JSON response. Dates display in UTC explicitly.
This is a bounded recent-project view, not a total project count or saved-work
list. Empty authorized profiles use a generic welcome without inventing names.

Each client route visit rechecks session and reloads the summary. The controller
clears previous private data before loading, aborts on navigation/logout and
rejects stale replies. Failed reads show retry; expired identity returns to
login/verification. The renderer requires summary/workspace IDs to match the
authorized session before displaying personalization. Logout clears profile and
workspace data before server confirmation.

## Persistence and release gates

No database objects or dependencies are added by the UI itself. OPU-97 provides
profile/preference edits, project CRUD and saved investigations with CSRF and
persistence; a complete account event feed remains outside this increment.
Do not enable a write control by changing a client flag alone. Client live
integrations retain the separate tenant isolation gate.

Provider login/callback code is implemented; hosting and actual browser acceptance
are delegated to the other engineer. The separate same-origin `orchestrator.client`
entry point serves the UI/account APIs; the static preview cannot supply this
journey. Before release, complete real
signup/login-to-workspace, refresh, settings navigation, account-switch/logout,
two-client denial and browser/keyboard/screen-reader checks before release.
The new summary reads have controlled provider tests, not hosted Supabase evidence.

Rollback the frontend/backend application deployment together if this contract
must be withdrawn. This change has no migration or data to reverse. Preserve
existing demo history and the additive schema from previous work packages.
