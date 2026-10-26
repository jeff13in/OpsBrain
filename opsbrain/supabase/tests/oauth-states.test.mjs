import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { PGlite } from '@electric-sql/pglite';

const hash = 'b'.repeat(64);
const verifier = 'v'.repeat(86);
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
    '202610120003_workspace_persistence.sql', '202610120004_account_flows.sql', '202610260005_oauth_states.sql']) {
    await db.exec(await readFile(new URL('../migrations/' + file, import.meta.url), 'utf8'));
  }
});
after(async () => { if (db) await db.close(); });

function asRole(role, run) {
  return db.transaction(async tx => { await tx.exec(`set local role ${role}`); return run(tx); });
}

test('auth store inserts and consumes a verifier exactly once', async () => {
  await asRole('opsbrain_auth_store', tx => tx.query('insert into opsbrain_private.oauth_states values ($1,$2,$3)', [hash, verifier, 2000]));
  const first = await asRole('opsbrain_auth_store', tx => tx.query('delete from opsbrain_private.oauth_states where state_hash=$1 returning *', [hash]));
  const second = await asRole('opsbrain_auth_store', tx => tx.query('delete from opsbrain_private.oauth_states where state_hash=$1 returning *', [hash]));
  assert.equal(first.rows[0].code_verifier, verifier);
  assert.equal(second.rows.length, 0);
});

test('malformed state hashes and verifiers are rejected', async () => {
  for (const [key, value] of [['short', verifier], [hash, 'x'], [hash, 'bad verifier'.repeat(5)]]) {
    await assert.rejects(asRole('opsbrain_auth_store', tx => tx.query('insert into opsbrain_private.oauth_states values ($1,$2,1)', [key, value])));
  }
});

test('client roles cannot read or write verifiers', async () => {
  await db.query('insert into opsbrain_private.oauth_states values ($1,$2,2000)', ['c'.repeat(64), verifier]);
  for (const role of ['anon', 'authenticated', 'service_role', 'opsbrain_session_store']) {
    await assert.rejects(asRole(role, tx => tx.query('select * from opsbrain_private.oauth_states')), e => e.code === '42501');
    await assert.rejects(asRole(role, tx => tx.query('insert into opsbrain_private.oauth_states values ($1,$2,1)', ['d'.repeat(64), verifier])));
  }
});
