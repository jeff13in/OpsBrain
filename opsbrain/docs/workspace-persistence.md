# OPU-97 account persistence

Implemented locally October 12, 2026, under the free-only budget. Apply migrations
001/002 then 003 to the application Supabase database, not operational RAG storage.
No hosted migration or client data collection occurred in this increment.

## Data and authorization

Migration 003 adds profile preferences/version/update time, owner-private
saved_work, workspace retry receipts and deletion tombstones. Saved work has a
composite workspace/project FK with cascading deletion. Existing retry-safe
personal workspace provisioning remains the OPU-93 service-only bootstrap.
Ordinary profile/project/saved-work reads and writes use the verified user's
provider JWT and existing RLS, never privileged session-store credentials. Ownership derives from auth.uid()
and membership; client owner IDs/profile target IDs are rejected. Workspace,
project links and ownership cannot be patched.

Preferences currently include default_section (dashboard/projects/tools) and
reduced_motion. The client honors the start page on a plain Workspace landing and
the motion preference while in the authorized account context. Role/permission
keys and arbitrary preferences are rejected. Profile and record updates use
positive expected versions; server triggers advance versions. Stale updates or
deletions return a safe 409 and require a fresh read.

## API and retry contract

GET `/api/workspaces/{uuid}/records/{kind}` lists projects or saved_work, at most
20 per page, ordered by UUID. next_cursor is the last visible UUID when a next
page exists. GET with an additional record UUID reads one authorized record.
Saved-work lists omit payload; individual reads return the bounded payload.
All successful responses are no-store; malformed scope/provider failures never
substitute previous-user or synthetic account records.

POST `/api/workspaces/{uuid}/mutations` requires exact Origin and a session-bound
X-CSRF-Token. The bounded body carries request_id, operation, record_id,
expected_version and changes. Operations: project.create/update/delete,
saved.create/update/delete, profile.update. Creates use version zero and a stable
new record UUID. Updates/deletes require the current positive version. Profile
commands omit record_id; the backend supplies the verified user ID. Field
allowlists reject owner changes and hidden context. Requests over 150,000 bytes
are rejected before model parsing.

The backend calls the SECURITY INVOKER workspace_mutate RPC with the user JWT.
It verifies ownership, serializes workspace mutations with a transaction advisory
lock, fingerprints the exact command using SHA-256 and stores a compact receipt.
Retrying the same request UUID/body returns the original result; changing its
payload conflicts. The browser retains a failed command only in page memory and
offers an exact retry. A confirmed write reloads authoritative records; reload
failure is reported separately from write failure. Navigation/logout clear the
command and reject late replies.

Clients cannot insert/update retry receipts or deletion tombstones directly.
Narrow fixed-search-path definer helpers write only that metadata: the receipt
helper rechecks workspace ownership, and the deletion trigger derives metadata
from the deleted authorized row. The private schema must remain outside Data API
exposure. Record CRUD itself remains SECURITY INVOKER and protected by RLS.

## Saved investigations and UI

The first saved record is a Demo investigation: title, project, mode and one to
twenty displayed question/response turns. Preserve answer text, source references
and up to four per-agent status/answer/source/error outcomes. Hidden reasoning,
provider tokens, SDK context and arbitrary metadata are not accepted by the API.
The canonical payload is bounded to 128 KiB; question/answer/source/error fields
also have individual bounds. Live provenance is rejected until client integrations
are isolated. The database enforces owner/FK, coarse payload shape/provenance and
byte/turn limits; the API enforces the nested display-field schema.

Saving is an explicit action on Demo chat with a project selection. Reopening
fetches the account record anew and shows the preserved conversation in Projects,
where its title can be updated or it can be deleted. It does not resume a live
agent session or silently write restored private content into browser demo history.
Browser demo history keeps its existing separate 72-hour retention.

## Retention, deletion, quotas and backups

Account projects/investigations remain until explicit deletion. No account expiry
job is added. Project deletion discloses child investigation deletion and requires
an explicit confirmation action. SQL delete triggers record tombstones, including
cascaded children; create retries using deleted IDs are denied even with a new
request UUID. Cached receipts cannot resurrect deleted records. Client state is
cleared/reloaded following deletion. Deleting a provider account cascades owned
workspace records, memberships, receipts, tombstones and private sessions. The
account-closure provider/admin workflow is still a release prerequisite; no public
account-deletion endpoint is added by this increment.

Initial engineering limits are 100 projects and 100 saved investigations per
workspace, 128 KiB per payload, and 5,000 non-delete retry receipts. Database
insert guards enforce record limits even on direct user-role inserts. At the
receipt limit, new creates/updates stop; authorized deletions remain allowed and
may add deletion receipts beyond that threshold. Pagination is bounded to twenty
rows. The beta owner must confirm capacity/receipt-maintenance policy against the
free provider quota before release. Do not auto-purge account work or deletion
tombstones to make space. Raising limits does not authorize a paid upgrade.

No hosted backups were configured. Free Supabase's backup limitation remains as
recorded in the setup plan. Manual encrypted export/restore, who owns backups,
where copies live and the actual backup/deletion window must be agreed before
collecting client work. Deletion removes active records but cannot promise
immediate erasure of older backup copies. Receipts store fingerprints/results,
not duplicated question bodies; tombstones retain only workspace/record IDs until
workspace closure. Keep private session backup keys protected separately.

## Verification and remaining gates

Local PostgreSQL tests cover receipts/retries, version conflicts, RLS denial,
composite FKs, child deletion/tombstones, preferences, quotas and provider-account
closure cleanup. API and frontend tests use controlled provider/DOM responses.
Production provider login/callbacks, staging migration and PostgREST acceptance,
real save→logout→login→reopen, browser/mobile/assistive technology, concurrency
across replicas and backup/restore remain open. The user delegated these hosted
checks to the other engineer. Local completion does not establish a client release.

Rollback application wiring together with its API contract while retaining the
additive schema and account data. Never drop/reset a shared database. Use the
tested restore/reconciliation plan if a schema restoration is necessary.
