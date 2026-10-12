import { after, before, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';

const a = '00000000-0000-4000-8000-000000000001';
const b = '00000000-0000-4000-8000-000000000002';
const unverified = '00000000-0000-4000-8000-000000000003';
const unapproved = '00000000-0000-4000-8000-000000000004';
let db, wa, wb, pa, pb;

// PGlite runs PostgreSQL locally. Only the provider-owned auth schema and roles
// are stubbed here; migrations, grants, constraints and RLS run as actual SQL.
before(async () => {
  db = new PGlite();
  await db.exec(`
    create role anon;
    create role authenticated;
    create role service_role bypassrls;
    create schema auth;
    create table auth.users (id uuid primary key, email_confirmed_at timestamptz);
    create function auth.uid() returns uuid language sql stable as $$
      select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
    $$;
    grant usage on schema auth to anon, authenticated, service_role;
    grant execute on function auth.uid() to anon, authenticated, service_role;
    -- Simulate Supabase defaults to prove the migration revokes broad grants.
    alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
  `);
  await db.exec(await readFile(new URL('../migrations/202610120001_workspace_foundation.sql', import.meta.url), 'utf8'));
  await db.query(`insert into auth.users values ($1, now()), ($2, now()), ($3, null), ($4, now())`, [a, b, unverified, unapproved]);
  await db.query(`insert into opsbrain_private.beta_approvals (user_id) values ($1), ($2), ($3)`, [a, b, unverified]);
  wa = (await asRole('service_role', '', tx => tx.query('select public.provision_personal_workspace($1) as id', [a]))).rows[0].id;
  wb = (await asRole('service_role', '', tx => tx.query('select public.provision_personal_workspace($1) as id', [b]))).rows[0].id;
  await asRole('authenticated', a, tx => tx.query('insert into public.projects (workspace_id, title) values ($1, $2)', [wa, 'A project']));
  await asRole('authenticated', b, tx => tx.query('insert into public.projects (workspace_id, title) values ($1, $2)', [wb, 'B project']));
  pa = (await db.query('select id from public.projects where workspace_id=$1', [wa])).rows[0].id;
  pb = (await db.query('select id from public.projects where workspace_id=$1', [wb])).rows[0].id;
});

after(async () => { if (db) await db.close(); });

async function asRole(role, user, run) {
  assert.ok(['anon', 'authenticated', 'service_role'].includes(role));
  return db.transaction(async tx => {
    await tx.exec(`set local role ${role}`);
    await tx.query("select set_config('request.jwt.claim.sub', $1, true)", [user]);
    return run(tx);
  });
}

async function denied(role, user, sql, params = [], code = '42501') {
  await assert.rejects(asRole(role, user, tx => tx.query(sql, params)), error => error.code === code);
}

test('clean migration enables RLS on all application and private tables', async () => {
  const result = await db.query(`select relname, relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where n.nspname in ('public', 'opsbrain_private') and c.relkind='r' order by relname`);
  assert.equal(result.rows.length, 5);
  assert.ok(result.rows.every(row => row.relrowsecurity));
});

test('bootstrap retries preserve one workspace and membership', async () => {
  const retry = await asRole('service_role', '', tx => tx.query('select public.provision_personal_workspace($1) as id', [a]));
  assert.equal(retry.rows[0].id, wa);
  assert.equal((await db.query('select count(*)::int as n from public.workspace_members where user_id=$1', [a])).rows[0].n, 1);
});

test('bootstrap requires verification and beta approval', async () => {
  for (const user of [unverified, unapproved]) {
    await denied('service_role', '', 'select public.provision_personal_workspace($1)', [user]);
  }
  assert.equal((await db.query('select count(*)::int as n from public.workspaces')).rows[0].n, 2);
});

test('anonymous SELECT INSERT UPDATE DELETE are denied for every client table', async () => {
  for (const table of ['profiles', 'workspaces', 'workspace_members', 'projects']) {
    for (const sql of [
      `select * from public.${table}`,
      `insert into public.${table} default values`,
      `update public.${table} set ${table === 'profiles' ? 'display_name' : table === 'workspaces' ? 'name' : table === 'projects' ? 'title' : 'role'}='forged'`,
      `delete from public.${table}`,
    ]) await denied('anon', '', sql);
  }
});

test('each identity sees only its profile, workspace, memberships and projects', async () => {
  for (const [user, workspace, project] of [[a, wa, pa], [b, wb, pb]]) {
    for (const [table, column, expected] of [
      ['profiles', 'user_id', user], ['workspaces', 'id', workspace],
      ['workspace_members', 'workspace_id', workspace], ['projects', 'id', project],
    ]) {
      const result = await asRole('authenticated', user, tx => tx.query(`select ${column} from public.${table}`));
      assert.deepEqual(result.rows, [{ [column]: expected }]);
    }
  }
});

test('authenticated role with no identity gets no rows and cannot insert', async () => {
  assert.equal((await asRole('authenticated', '', tx => tx.query('select * from public.projects'))).rows.length, 0);
  await denied('authenticated', '', 'insert into public.projects (workspace_id, title) values ($1, $2)', [wa, 'forged']);
});

test('cross-user read/update/delete cannot reach another project', async () => {
  for (const [user, project] of [[a, pb], [b, pa]]) {
    for (const sql of [
      'select * from public.projects where id=$1',
      "update public.projects set title='forged' where id=$1 returning id",
      'delete from public.projects where id=$1 returning id',
    ]) assert.equal((await asRole('authenticated', user, tx => tx.query(sql, [project]))).rows.length, 0);
  }
});

test('cross-workspace project insertion and forged ownership are denied', async () => {
  await denied('authenticated', a, 'insert into public.projects (workspace_id, title) values ($1, $2)', [wb, 'forged']);
  await denied('authenticated', a, 'insert into public.projects (workspace_id, creator_id, title) values ($1, $2, $3)', [wa, b, 'forged']);
});

test('immutable project ownership, workspace, id and version cannot be patched', async () => {
  for (const [column, value] of [['creator_id', b], ['workspace_id', wb], ['id', pb], ['version', 99]]) {
    await denied('authenticated', a, `update public.projects set ${column}=$1 where id=$2`, [value, pa]);
  }
});

test('authorized project CRUD works and update advances server version', async () => {
  await asRole('authenticated', a, async tx => {
    await tx.query('insert into public.projects (workspace_id, title) values ($1, $2)', [wa, 'temporary']);
    const inserted = (await tx.query("select id, version from public.projects where title='temporary'")).rows[0];
    assert.equal(Number(inserted.version), 1);
    await tx.query('update public.projects set title=$1 where id=$2', ['changed', inserted.id]);
    const updated = (await tx.query('select title, version from public.projects where id=$1', [inserted.id])).rows[0];
    assert.equal(updated.title, 'changed');
    assert.equal(Number(updated.version), 2);
    assert.equal((await tx.query('delete from public.projects where id=$1 returning id', [inserted.id])).rows.length, 1);
  });
});

test('clients cannot create or mutate membership, approval or provisioning privileges', async () => {
  await denied('authenticated', a, 'insert into public.workspace_members (workspace_id, user_id) values ($1,$2)', [wb, a]);
  await denied('authenticated', a, "update public.workspace_members set role='owner' where workspace_id=$1", [wb]);
  await denied('authenticated', a, 'delete from public.workspace_members where workspace_id=$1', [wa]);
  await denied('authenticated', a, 'select * from opsbrain_private.beta_approvals');
  await denied('authenticated', a, 'insert into opsbrain_private.beta_approvals (user_id) values ($1)', [unapproved]);
  await denied('authenticated', a, 'select public.provision_personal_workspace($1)', [a]);
  await denied('anon', '', 'select public.provision_personal_workspace($1)', [a]);
});

test('profile and workspace edits are scoped, immutable identities remain protected', async () => {
  await asRole('authenticated', a, async tx => {
    await tx.query('update public.profiles set display_name=$1 where user_id=$2', ['User A', a]);
    await tx.query('update public.workspaces set name=$1 where id=$2', ['A workspace', wa]);
    assert.equal((await tx.query('update public.profiles set display_name=$1 where user_id=$2 returning user_id', ['forged', b])).rows.length, 0);
    assert.equal((await tx.query('update public.workspaces set name=$1 where id=$2 returning id', ['forged', wb])).rows.length, 0);
  });
  await denied('authenticated', a, 'update public.profiles set user_id=$1 where user_id=$2', [b, a]);
  await denied('authenticated', a, 'update public.workspaces set personal_owner_id=$1 where id=$2', [b, wa]);
  await denied('authenticated', a, 'insert into public.profiles (user_id) values ($1)', [a]);
  await denied('authenticated', a, 'delete from public.workspaces where id=$1', [wa]);
});

test('revoking beta approval removes read and write access to existing records', async () => {
  await db.transaction(async tx => {
    await tx.query('delete from opsbrain_private.beta_approvals where user_id=$1', [b]);
    await tx.exec('set local role authenticated');
    await tx.query("select set_config('request.jwt.claim.sub', $1, true)", [b]);
    assert.equal((await tx.query('select * from public.projects')).rows.length, 0);
    assert.equal((await tx.query("update public.projects set title='forged' where id=$1 returning id", [pb])).rows.length, 0);
    // This isolated transaction rolls back deliberately to preserve fixtures.
    throw new Error('rollback fixture');
  }).catch(error => { assert.equal(error.message, 'rollback fixture'); });
});

test('workspace FK and bounded title constraints reject invalid project rows', async () => {
  await assert.rejects(db.query('insert into public.projects (workspace_id, creator_id, title) values ($1, $2, $3)', [unapproved, a, 'invalid']), error => error.code === '23503');
  for (const title of ['', '   ', 'x'.repeat(201)]) {
    await denied('authenticated', a, 'insert into public.projects (workspace_id, title) values ($1, $2)', [wa, title], '23514');
  }
});
