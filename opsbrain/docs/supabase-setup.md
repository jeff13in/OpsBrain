# OPU-93 setup kickoff

Started October 12, 2026. This increment adds an offline configuration preflight,
environment template and versioned database foundation tested in local PostgreSQL.
It does not provision a hosted project, connect the app or implement authentication.

## Free-tier constraint

The user requires everything to be free. Use local development and, subject to
available account quota, separate free staging/production Supabase projects.
Supabase currently limits Free to two active projects, 500 MB of database storage
per project and pauses inactive projects after a week. Automatic backups and
branching are not included. Do not create a third hosted development project,
enable paid add-ons or upgrade. The earlier three-hosted-project proposal is
superseded by local development plus two isolated hosted environments.

The API host, free SMTP provider and sender identity are still unselected;
free Supabase alone does not supply those deployment decisions. Use provider
subdomains where available rather than requiring a purchased domain. Storage
quotas and manual backup/deletion windows must be agreed before client release.
See [current Supabase plan limits](https://supabase.com/pricing).

## Deployment inputs

Record development, staging and production separately: project identifier,
Supabase region and budget, API-capable host, HTTPS application origin, access
owner and SMTP sender/domain. Supply credentials through the host's secret
manager rather than issue descriptions or chat. The architecture and local
implementation are reviewed in the OPU-92–98 closure evidence; hosted setup
and acceptance are delegated to the other engineer by the user.
The approved beta identity list is still needed before provisioning users.

## Local preflight

Export APP_ENV, APP_ORIGIN, SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY through
your chosen environment tooling, then run from `opsbrain/`:

```sh
python3 scripts/check_workspace_environment.py
python3 -m unittest discover -s tests -p 'test_workspace_environment.py'
```

The script reads process environment only, performs no network requests and
prints variable names rather than values. It checks origin shape, environment
selection and publishable-key type. Loopback HTTP is allowed only in development.
An exit status of zero verifies configuration shape; it does not prove keys are
valid, projects are separate, or provider connectivity works. New project setup
uses current publishable keys. Legacy JWT key deployments require an explicit
migration decision; do not substitute a secret/service-role key.

## Remaining implementation sequence

1. Accept the architecture, select the host/private durable session store and
   confirm provider projects and environment isolation.
2. Select compatible Python 3.11 provider, encryption and migration tooling;
   prove basic connectivity without logging provider response bodies or secrets.
3. Validate the foundation migration against a real development Supabase instance,
   then staging. Local SQL/RLS checks described below already pass. Add saved-work
   entities/composite workspace foreign keys with OPU-97's persistence contract.
4. Wire the service-only provisioning RPC into verified backend onboarding; derive
   its target identity from the server session. Preserve the operational RAG database.
5. Configure exact server callback URLs and production SMTP; test verification,
   expiry, replay and recovery. URL fragments cannot serve as server callbacks.
6. Record migration, restore and rollback evidence before marking OPU-93 ready
   for review. Apply migrations to development, then staging, then production
   only after environment-specific validation and a recorded backup/restore plan.

## Database foundation and verification

`supabase/migrations/202610120001_workspace_foundation.sql` creates profiles,
personal workspaces, owner memberships, projects and a private beta approval
table. It enables RLS, revokes inherited broad grants and grants only permitted
columns. Ownership fields and membership writes are unavailable to client roles.
Private helpers use fixed search paths and identity from `auth.uid()`.

The service-role-only `public.provision_personal_workspace(uuid)` requires a
verified approved provider identity and provisions profile/workspace/membership
in one transaction. Retried calls reuse the workspace. Use administrative
credentials only for this narrow bootstrap and approval administration. Normal
CRUD must carry the user's JWT and publishable key. Never expose
`opsbrain_private` as a Supabase Data API schema. Approval rows are keyed to
provider user UUIDs; granting beta eligibility is a server administrator action.

From `opsbrain/supabase/`:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm test
```

Fourteen tests run the actual migration, grants, policies and constraints through
PGlite (PostgreSQL in WebAssembly). Only Supabase-owned Auth tables/functions and
roles are synthetic. Coverage includes clean migration, anonymous CRUD denial,
two-user isolation, own project CRUD, forged ownership, immutable columns,
membership escalation, approval revocation and bootstrap retries. CI runs the
suite as Workspace Migration & RLS. PGlite is a dev dependency only, outside the
public build and service images. It is not a Supabase Auth server: provider JWT
verification, PostgREST, email, concurrent replicas and hosted configuration still
need acceptance checks. Conversation storage and session encryption are later
increments; no saved-work/composite conversation FK coverage is claimed here.

## Applying and rolling back

Current implementation includes four ordered migrations, user-JWT verified
onboarding (no administrative key in request handling), encrypted server sessions,
durable recovery/CSRF contexts and database rate buckets. The dedicated login
needs both `opsbrain_session_store` and `opsbrain_auth_store`; it must never have
public client CRUD or administrative memberships. Admins manage private beta
email hashes and UUID approvals. See [account configuration](account-authentication.md)
and the [release runbook](client-release-runbook.md). Historical foundation
evidence above remains a record of the first increment.

Do not apply this application migration to the existing RAG database. Before a
hosted apply, identify the exact environment and project, check the migration
history and take a manual encrypted backup of existing application records and
schema using the project's documented database export process. Keep backups in
private storage and prove a restore in an isolated development database. Free
does not include automatic backups; a successful export without a restore test
does not establish recoverability.

Use the Supabase migration workflow to apply versioned files to development,
then staging; record project identifiers, migration version and test results.
Supabase Auth must supply `auth.users`, `auth.uid()` and provider roles. This
migration runs inside a transaction; an apply error rolls it back. Never rerun
an already recorded migration as ad-hoc SQL. Production application wiring waits
for the identity/hosting/session/SMTP decisions and staging acceptance.

To roll back application wiring after a successful apply, restore the previous
application deployment and disable client workspace ingress while retaining the
new schema and data. Do not drop tables or reset a shared database. If the schema
itself must be reverted, restore the tested backup into an isolated replacement
and reconcile post-backup client writes before switching. No destructive down
migration is provided. Configuration templates remain commented out and the
preflight is not wired into startup.

Shared live integrations remain behind the separate client isolation gate.
Week 5 targets October 16 and Week 6 October 23 in Linear, but the project target
still says October 7 and capacity remains unconfirmed.

References: [architecture contract](../architecture/client-workspace.md),
[Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys),
[environment management](https://supabase.com/docs/guides/deployment/managing-environments),
[callback allowlists](https://supabase.com/docs/guides/auth/redirect-urls).
