import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';

const user = '00000000-0000-4000-8000-000000000001';
const hash = 'a'.repeat(64);
let db;
before(async () => {
  db = new PGlite();
  await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
    create schema auth; create table auth.users (id uuid primary key, email_confirmed_at timestamptz);
    create function auth.uid() returns uuid language sql stable as $$ select null::uuid $$;
    grant usage on schema auth to anon, authenticated, service_role;
    alter default privileges in schema public grant all on tables to anon, authenticated, service_role;`);
  for (const file of ['202610120001_workspace_foundation.sql', '202610120002_private_sessions.sql']) {
    await db.exec(await readFile(new URL('../migrations/' + file, import.meta.url), 'utf8'));
  }
  await db.query('insert into auth.users values ($1, now())', [user]);
});
after(async () => { if (db) await db.close(); });

function asRole(role, run) {
  assert.ok(['anon', 'authenticated', 'service_role', 'opsbrain_session_store'].includes(role));
  return db.transaction(async tx => { await tx.exec(`set local role ${role}`); return run(tx); });
}

test('session migration applies after workspace migration and enables RLS', async () => {
  const result = await db.query("select relrowsecurity from pg_class where oid='opsbrain_private.app_sessions'::regclass");
  assert.equal(result.rows[0].relrowsecurity, true);
});

test('client and general service roles cannot read or write private session records', async () => {
  for (const role of ['anon', 'authenticated', 'service_role']) {
    for (const sql of ['select * from opsbrain_private.app_sessions', 'insert into opsbrain_private.app_sessions default values',
      'update opsbrain_private.app_sessions set last_seen_at=0', 'delete from opsbrain_private.app_sessions']) {
      await assert.rejects(asRole(role, tx => tx.query(sql)), error => error.code === '42501');
    }
  }
});

test('dedicated server role supports session CRUD and refresh row locking', async () => {
  await asRole('opsbrain_session_store', async tx => {
    await tx.query('insert into opsbrain_private.app_sessions values ($1,$2,$3,2000,10000,1000)', [hash, user, 'ciphertext'.repeat(20)]);
    const record = (await tx.query('select * from opsbrain_private.app_sessions where session_hash=$1 for update', [hash])).rows[0];
    assert.equal(record.user_id, user);
    await tx.query('update opsbrain_private.app_sessions set token_ciphertext=$1,last_seen_at=1500 where session_hash=$2', ['rotated-ciphertext'.repeat(20), hash]);
  });
  // A new transaction reads persisted rotation, rather than a process-local cache.
  await asRole('opsbrain_session_store', async tx => {
    assert.equal(Number((await tx.query('select last_seen_at from opsbrain_private.app_sessions where session_hash=$1', [hash])).rows[0].last_seen_at), 1500);
    await tx.query('delete from opsbrain_private.app_sessions where session_hash=$1', [hash]);
    assert.equal((await tx.query('select * from opsbrain_private.app_sessions')).rows.length, 0);
  });
});

test('session capability cannot read application records or issue bootstrap memberships', async () => {
  for (const sql of ['select * from public.profiles', 'select * from public.workspaces', 'select * from opsbrain_private.beta_approvals',
    `select public.provision_personal_workspace('${user}')`]) {
    await assert.rejects(asRole('opsbrain_session_store', tx => tx.query(sql)), error => error.code === '42501');
  }
});
