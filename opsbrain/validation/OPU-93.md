# OPU-93 local infrastructure increment

Current closure: local implementation is complete under the user-directed
handoff. Hosted setup and release acceptance are tracked separately in OPU-99.
See [final cross-ticket evidence](week5-closure.md). The report below records
earlier increments and does not define the current completion scope.

October 12, 2026. Linear status: In Progress. User confirmed OPU-93 is the next
work package and all infrastructure must be free.

Implemented an offline environment preflight, optional server settings template,
versioned application schema, private beta approvals, service-only transactional
workspace provisioning, indexed RLS, column grants and server-owned project
version updates. Added a pinned PGlite development dependency and CI job to run
actual PostgreSQL migration/access-policy tests. Existing RAG data, application
routes, frontend assets and service dependencies are unchanged.

Verification: six environment unit tests passed; fourteen local PostgreSQL tests
passed with no skips. SQL tests cover clean apply, anonymous CRUD denial,
two-user isolation, project CRUD, ownership forgery, immutable columns, privilege
escalation, approval revocation, FK/title constraints and bootstrap retries.
Provider Auth tables/roles are synthetic. Hosted Supabase, email, Python 3.11
integration and multi-replica concurrency have not been tested. The GitHub CI job
has been added locally but has not run remotely.

Database objects: public profiles/workspaces/workspace_members/projects; private
beta_approvals; private approval/workspace helpers and project-version trigger;
public service-only provision_personal_workspace RPC. No hosted database changed.
Conversations, turn storage and cross-workspace conversation/project constraints
remain OPU-97 work. Session-store encryption/provider integration remain open.

The free-tier plan uses local development plus separate free staging/production
projects subject to available quota. No paid resources or account upgrades were
created. API host, Supabase project/region, SMTP sender/provider, private durable
session store and approved client identities remain required. OPU-92 remains
In Review. Keep OPU-93 In Progress until hosted connectivity, migration/RLS and
provider acceptance evidence is recorded.

See [setup instructions and rollback approach](../docs/supabase-setup.md).
