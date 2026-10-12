import { before, after, test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { PGlite } from '@electric-sql/pglite';
let db, wa, wb;
const a='00000000-0000-4000-8000-000000000001', b='00000000-0000-4000-8000-000000000002';
const project=randomUUID(), saved=randomUUID();
const payload={mode:'demo',turns:[{question:'Why is this slow?',response:{status:'ok',answer:'Example answer [1]',sources:['Example runbook'],results:[]}}]};
before(async()=>{
 db=new PGlite();
 await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
 create schema auth; create table auth.users(id uuid primary key,email_confirmed_at timestamptz);
 create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
 grant usage on schema auth to authenticated,anon,service_role;`);
 for(const name of ['202610120001_workspace_foundation.sql','202610120002_private_sessions.sql','202610120003_workspace_persistence.sql']) await db.exec(await readFile(new URL('../migrations/'+name,import.meta.url),'utf8'));
 await db.query('insert into auth.users values($1,now()),($2,now())',[a,b]);
 await db.query('insert into opsbrain_private.beta_approvals(user_id) values($1),($2)',[a,b]);
 wa=(await db.query('select public.provision_personal_workspace($1) as id',[a])).rows[0].id;
 wb=(await db.query('select public.provision_personal_workspace($1) as id',[b])).rows[0].id;
});
after(async()=>{if(db)await db.close();});
async function asUser(user,fn){return db.transaction(async tx=>{await tx.exec('set local role authenticated');await tx.query("select set_config('request.jwt.claim.sub',$1,true)",[user]);return fn(tx);});}
async function mutate(user,ws,op,id,version,changes,key=randomUUID()){
 return asUser(user,async tx=>(await tx.query('select public.workspace_mutate($1,$2,$3,$4,$5,$6) as result',[key,ws,op,id,version,changes])).rows[0].result);
}

test('project create retry is idempotent and changed retry payload conflicts',async()=>{
 const key=randomUUID(); const one=await mutate(a,wa,'project.create',project,0,{title:'My project'},key);
 assert.deepEqual(await mutate(a,wa,'project.create',project,0,{title:'My project'},key),one);
 await assert.rejects(mutate(a,wa,'project.create',project,0,{title:'Changed'},key),e=>e.code==='40001');
 assert.equal((await db.query('select count(*)::int n from public.projects')).rows[0].n,1);
});
test('project versions prevent lost updates',async()=>{
 const next=await mutate(a,wa,'project.update',project,1,{title:'Updated'});assert.equal(next.version,2);
 await assert.rejects(mutate(a,wa,'project.update',project,1,{title:'Stale'}),e=>e.code==='40001');
});
test('saved work persists sources/provenance through a fresh user transaction',async()=>{
 await mutate(a,wa,'saved.create',saved,0,{title:'Investigation',project_id:project,payload});
 const rows=await asUser(a,tx=>tx.query('select payload from public.saved_work where id=$1',[saved]));
 assert.deepEqual(rows.rows[0].payload,payload);
 assert.equal((await asUser(b,tx=>tx.query('select * from public.saved_work'))).rows.length,0);
 await assert.rejects(mutate(b,wa,'saved.delete',saved,1,{}),e=>e.code==='42501');
});
test('cross-workspace project links and forged owner updates are denied',async()=>{
 await assert.rejects(mutate(b,wb,'saved.create',randomUUID(),0,{title:'Forged',project_id:project,payload}),e=>e.code==='23503');
 await assert.rejects(asUser(a,tx=>tx.query('update public.saved_work set owner_id=$1 where id=$2',[b,saved])),e=>e.code==='42501');
});
test('preferences survive a new session and reject unknown permission fields',async()=>{
 await mutate(a,wa,'profile.update',a,1,{display_name:'User A',preferences:{default_section:'projects',reduced_motion:true}});
 assert.equal((await asUser(a,tx=>tx.query('select preferences from public.profiles'))).rows[0].preferences.reduced_motion,true);
 await assert.rejects(mutate(a,wa,'profile.update',a,2,{display_name:'User A',preferences:{default_section:'projects',reduced_motion:true,role:'admin'}}),e=>e.code==='23514');
});
test('project deletion cleans children and old create retries cannot resurrect records',async()=>{
 const id=randomUUID(),key=randomUUID();await mutate(a,wa,'project.create',id,0,{title:'Delete me'},key);
 await mutate(a,wa,'saved.create',randomUUID(),0,{title:'Child',project_id:id,payload});
 const delKey=randomUUID();await mutate(a,wa,'project.delete',id,1,{},delKey);
 assert.equal((await db.query('select * from public.saved_work where project_id=$1',[id])).rows.length,0);
 assert.equal((await mutate(a,wa,'project.delete',id,1,{},delKey)).deleted,true);
 await assert.rejects(mutate(a,wa,'project.create',id,0,{title:'Delete me'},key),e=>e.code==='P0002');
 await assert.rejects(mutate(a,wa,'project.create',id,0,{title:'Again'}),e=>e.code==='P0002');
});
test('anonymous persistence table reads and mutations are denied',async()=>{
 for(const table of ['saved_work','workspace_receipts','workspace_tombstones']) await assert.rejects(db.transaction(async tx=>{await tx.exec('set local role anon');await tx.query(`select * from public.${table}`);}),e=>e.code==='42501');
});
test('users cannot forge retry receipts or deletion tombstones through table writes',async()=>{
 await assert.rejects(asUser(a,tx=>tx.query('insert into public.workspace_tombstones values($1,$2)',[wa,randomUUID()])),e=>e.code==='42501');
 await assert.rejects(asUser(a,tx=>tx.query('insert into public.workspace_receipts values($1,$2,$3,$4)',[wa,randomUUID(),'a'.repeat(64),{}])),e=>e.code==='42501');
});
test('project quota is enforced even for direct user inserts',async()=>{
 await asUser(a,async tx=>{for(let i=0;i<99;i++)await tx.query('insert into public.projects(workspace_id,title) values($1,$2)',[wa,'Quota '+i]);});
 await assert.rejects(asUser(a,tx=>tx.query('insert into public.projects(workspace_id,title) values($1,$2)',[wa,'Too many'])),e=>e.code==='54000');
});
test('provider account closure cleans workspace records, receipts and sessions',async()=>{
 const id=randomUUID();await mutate(b,wb,'project.create',id,0,{title:'Account closure'});
 await mutate(b,wb,'saved.create',randomUUID(),0,{title:'Child',project_id:id,payload});
 await db.query('insert into opsbrain_private.app_sessions values($1,$2,$3,2000,10000,1000)',['b'.repeat(64),b,'synthetic-ciphertext'.repeat(10)]);
 await db.query('delete from auth.users where id=$1',[b]);
 for(const table of ['projects','saved_work','workspace_receipts','workspace_tombstones']) assert.equal((await db.query(`select * from public.${table} where workspace_id=$1`,[wb])).rows.length,0);
 assert.equal((await db.query('select * from opsbrain_private.app_sessions where user_id=$1',[b])).rows.length,0);
});
