import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';

const user = '00000000-0000-4000-8000-000000000001';
const other = '00000000-0000-4000-8000-000000000002';
const unverified = '00000000-0000-4000-8000-000000000003';
const hash = 'a'.repeat(64);
let db;
before(async () => {
  db = new PGlite();
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth; create table auth.users (id uuid primary key, email_confirmed_at timestamptz, email text,
      is_anonymous boolean default false, deleted_at timestamptz, banned_until timestamptz);
    create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true),'')::uuid $$;
    grant usage on schema auth to anon, authenticated, service_role;
    alter default privileges in schema public grant all on tables to anon, authenticated, service_role;`);
  for (const file of ['202610120001_workspace_foundation.sql', '202610120002_private_sessions.sql',
    '202610120003_workspace_persistence.sql', '202610120004_account_flows.sql']) {
    await db.exec(await readFile(new URL('../migrations/' + file, import.meta.url), 'utf8'));
  }
  await db.exec('create role test_backend; grant opsbrain_session_store, opsbrain_auth_store to test_backend;');
  await db.query('insert into auth.users (id,email_confirmed_at,email) values ($1,now(),$2),($3,now(),$4),($5,null,$6)',
    [user, 'A@Example.Test', other, 'b@example.test', unverified, 'unverified@example.test']);
  await db.query('insert into opsbrain_private.beta_invites values ($1,now()),($2,now())',
    ['a@example.test', 'unverified@example.test'].map(x => createHash('sha256').update(x).digest('hex')));
});
after(async () => { if (db) await db.close(); });

function asRole(role, subject, run) {
  assert.ok(['anon', 'authenticated', 'service_role', 'opsbrain_auth_store', 'opsbrain_session_store', 'test_backend'].includes(role));
  return db.transaction(async tx => {
    await tx.exec(`set local role ${role}`);
    await tx.query("select set_config('request.jwt.claim.sub',$1,true)", [subject || '']);
    return run(tx);
  });
}

test('verified invited user provisions exactly one workspace from JWT with no target parameter', async () => {
  const first = await asRole('authenticated', user, tx => tx.query('select public.ensure_personal_workspace() as id'));
  const retry = await asRole('authenticated', user, tx => tx.query('select public.ensure_personal_workspace() as id'));
  assert.equal(first.rows[0].id, retry.rows[0].id);
  assert.equal((await db.query('select * from public.workspaces')).rows.length, 1);
  assert.equal((await db.query('select * from public.workspace_members')).rows.length, 1);
  assert.equal((await db.query('select * from opsbrain_private.beta_approvals')).rows[0].user_id, user);
  await assert.rejects(asRole('authenticated', user, tx => tx.query('select public.ensure_personal_workspace($1)', [other])));
});

test('unverified, noninvited, anonymous and subject-free provisioning are denied', async () => {
  for (const [role, subject] of [['authenticated', other], ['authenticated', unverified], ['authenticated', null], ['anon', user]]) {
    await assert.rejects(asRole(role, subject, tx => tx.query('select public.ensure_personal_workspace()')), e => e.code === '42501');
  }
});

test('current banned, deleted or anonymous identity cannot use an older JWT to access records', async () => {
  for (const column of ['banned_until', 'deleted_at', 'is_anonymous']) {
    const value = column === 'is_anonymous' ? 'true' : column === 'banned_until' ? "now()+interval '1 day'" : 'now()';
    await db.exec(`update auth.users set ${column}=${value} where id='${user}'`);
    assert.equal((await asRole('authenticated', user, tx => tx.query('select * from public.workspaces'))).rows.length, 0);
    await assert.rejects(asRole('authenticated', user, tx => tx.query('select public.ensure_personal_workspace()')), e => e.code === '42501');
    await db.exec(`update auth.users set ${column}=${column === 'is_anonymous' ? 'false' : 'null'} where id='${user}'`);
  }
});

test('client/service/session capabilities cannot access private auth state or invitations', async () => {
  for (const role of ['anon', 'authenticated', 'service_role', 'opsbrain_session_store']) {
    for (const table of ['beta_invites', 'auth_flows', 'auth_rate_limits']) {
      for (const sql of [`select * from opsbrain_private.${table}`, `insert into opsbrain_private.${table} default values`,
        `update opsbrain_private.${table} set ${table === 'beta_invites' ? 'email_hash' : table === 'auth_flows' ? 'flow_hash' : 'bucket_hash'}='x'`,
        `delete from opsbrain_private.${table}`]) {
        await assert.rejects(asRole(role, user, tx => tx.query(sql)), e => e.code === '42501');
      }
    }
  }
});

test('auth capability can read invitations but cannot change eligibility or application records', async () => {
  assert.equal((await asRole('opsbrain_auth_store', null, tx => tx.query('select * from opsbrain_private.beta_invites'))).rows.length, 2);
  for (const sql of ['delete from opsbrain_private.beta_invites', 'select * from public.profiles',
    'select * from opsbrain_private.beta_approvals', 'select public.ensure_personal_workspace()']) {
    await assert.rejects(asRole('opsbrain_auth_store', null, tx => tx.query(sql)), e => e.code === '42501');
  }
});

test('durable recovery claim deletes one context and expires without replay', async () => {
  await asRole('opsbrain_auth_store', null, tx => tx.query('insert into opsbrain_private.auth_flows values ($1,$2,$3,1900)', [hash, user, 'encrypted'.repeat(30)]));
  const claim = async () => asRole('opsbrain_auth_store', null, tx => tx.query(
    'delete from opsbrain_private.auth_flows where flow_hash=$1 and expires_at>$2 returning *', [hash, 1000]));
  assert.equal((await claim()).rows.length, 1);
  assert.equal((await claim()).rows.length, 0);
  await asRole('opsbrain_auth_store', null, tx => tx.query('insert into opsbrain_private.auth_flows values ($1,null,null,1000)', [hash]));
  assert.equal((await claim()).rows.length, 0);
});

test('atomic rate buckets saturate and reset in a fresh window', async () => {
  const sql = `insert into opsbrain_private.auth_rate_limits values ($1,$2,1)
    on conflict (bucket_hash) do update set window_start=excluded.window_start,
    attempts=case when auth_rate_limits.window_start=excluded.window_start
      then least(auth_rate_limits.attempts+1,1000) else 1 end returning attempts`;
  for (let i = 1; i <= 7; i++) {
    assert.equal((await asRole('opsbrain_auth_store', null, tx => tx.query(sql, [hash, 900]))).rows[0].attempts, i);
  }
  assert.equal((await asRole('opsbrain_auth_store', null, tx => tx.query(sql, [hash, 1800]))).rows[0].attempts, 1);
});

test('combined backend capabilities support expired auth cleanup without public client access', async () => {
  await asRole('test_backend', null, async tx => {
    await tx.query('insert into opsbrain_private.app_sessions values ($1,$2,$3,2000,10000,1000)', [hash, user, 'encrypted'.repeat(30)]);
    await tx.query('insert into opsbrain_private.auth_flows values ($1,null,null,190000)', ['c'.repeat(64)]);
    await tx.query('insert into opsbrain_private.auth_rate_limits values ($1,99900,1)', ['c'.repeat(64)]);
    await tx.query('delete from opsbrain_private.auth_flows where expires_at<=100000');
    await tx.query('delete from opsbrain_private.auth_rate_limits where window_start<13600');
    await tx.query('delete from opsbrain_private.app_sessions where expires_at<=100000 or last_seen_at<=13600');
    assert.equal((await tx.query('select * from opsbrain_private.app_sessions')).rows.length, 0);
    assert.equal((await tx.query('select * from opsbrain_private.auth_flows')).rows.length, 1);
    assert.equal((await tx.query('select * from opsbrain_private.auth_rate_limits')).rows.length, 1);
  });
  assert.equal((await db.query('select * from public.workspaces')).rows.length, 1);
  await assert.rejects(asRole('test_backend', null, tx => tx.query('delete from public.projects')), e => e.code === '42501');
});

test('provider account closure removes recovery contexts and owned workspace data', async () => {
  await asRole('opsbrain_auth_store', null, tx => tx.query('insert into opsbrain_private.auth_flows values ($1,$2,$3,9000)', ['b'.repeat(64), user, 'encrypted'.repeat(30)]));
  await db.query('delete from auth.users where id=$1', [user]);
  assert.equal((await db.query('select * from opsbrain_private.auth_flows where user_id=$1', [user])).rows.length, 0);
  assert.equal((await db.query('select * from public.workspaces')).rows.length, 0);
});
