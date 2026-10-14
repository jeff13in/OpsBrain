# OPU-109 local passage foundation

October 13, 2026. The user authorized implementing the locally verifiable work
while hosted configuration remains deferred. This increment supplies the contract,
server resolver, authenticated route and browser adapter; it does not connect the
shared operational RAG database or enable client live tools.

## Contract and server boundary

GET /api/workspaces/{workspace_id}/investigations/{investigation_id}/sources/{source_id}

Workspace and investigation IDs are UUIDs. Source IDs are opaque lowercase
`src_` plus 64 hex characters. Labels, filesystem paths, symlinks and arbitrary
URLs are never interpreted as locations. Query parameters are rejected.

The existing SessionManager authenticates the provider identity and current
workspace membership, then holds the application session lock during resolution
so a locally revoked session cannot be revived between authentication and lookup.
The repository receives the server-derived user ID, authorized workspace ID,
investigation ID and source ID. The resolver independently rejects records with
different ownership/scope/source, revoked approval or expired retention.

The repository protocol returns a current approved RetrievedPassage, not a path.
It must read current investigation/source permissions and deletion/revocation
state on every lookup. There is no production in-memory repository, file resolver,
network URL fetcher or shared-RAG fallback. get_passage_resolver() defaults to
503. Only a reviewed tenant-aware adapter may replace that gate.

Available responses preserve the exact retrieved text (maximum 8,000 characters),
source ID, explicit retrieved provenance, optional bounded revision and optional
UTC observation timestamp. Missing, foreign, revoked and expired records share
one unavailable response with null text and metadata. Unknown revision/time
remain null; the resolver never generates an excerpt from an answer or reads a
new whole document. Malformed adapter results are rejected. Account response
policy adds no-store and private security headers to successes and failures and
redacts unexpected adapter failures.

This ownership model deliberately isolates individual users within workspaces.
Any future shared investigation policy requires an explicit server authorization
change; workspace membership alone does not authorize another user's passage.

## Browser preparation and current UI

sources.js validates the bounded contract. source-api.js calls only the fixed
same-origin scoped route with the application cookie, never provider tokens.
Its caller must supply verified identity and a separately approved live-source
capability. Login alone does not enable it. Unauthorized scopes and hostile
identifiers make no request. Identity changes, leave, new source requests,
deadlines and aborts clear private state and reject stale completion, including
transports that ignore abort. Responses are capped at 65,536 characters.

retrievedPassageDetails() renders validated text and metadata using the existing
HTML escaping and native details/summary controls. Missing metadata is disclosed.
Existing citation disclosures now support Escape to close and restore focus to
the invoking citation button. Synthetic Demo passage behavior remains unchanged.

The adapter and retrieved renderer are prepared exports, NOT wired into the
current Demo-only account tools or engineer API's label-only response.
Integration still needs authorized investigation/source references from the
retrieval pipeline. Existing report/source modules and the new adapter are in
both the Python client/static and Docker asset allowlists (17 files).

## Verification

- Full backend suite: 336 passed, one existing external RAG database test skipped;
  38 subtests passed. Dependency deprecation warnings remain.
- Frontend suite: 140 passed, including nine new passage contract, request,
  cancellation, escaping and keyboard fixture tests.
- Backend cases cover scoped lookup, foreign ownership/workspace/investigation,
  missing/revoked/expired records, malformed metadata and hostile IDs, anonymous
  denial, membership revocation, logout, disabled adapter and redacted failures.
- Static build and JavaScript syntax checks passed; 17 allowlisted assets.
- Python lint passed for changed backend files.
- Browser/DOM fixtures do not certify hosted provider isolation or screen-reader QA.

## Remaining integration and acceptance

1. Choose tenant-aware retrieved-snapshot storage and retention. Produce opaque
   source IDs and approved user/workspace/investigation bindings on the server
   from actual retrieved chunks. Preserve ingestion revision/observation metadata
   only when available; never attach a tenant ID to shared sources merely from
   browser input.
2. Implement the current-permission repository adapter with bounded queries and
   timeout, deletion/revocation semantics and least-privilege database access.
   Confirm isolation against two real identities before replacing the default gate.
3. Wire source references and the prepared renderer/controller into an authorized
   live investigation view. Reset the controller on navigation, logout, workspace
   and account changes; keep Demo fixtures separate and client live tools disabled
   until their approved capability is verified.
4. Run real Supabase/session/source-store and browser acceptance: isolation,
   revoked sources, provider outage, desktop/mobile, keyboard open/close/focus and
   screen-reader behavior. Hosted setup remains OPU-99/OPU-105.

No hosted migration, provider setting, deployment, account invitation, commit or
push was performed for this increment.
