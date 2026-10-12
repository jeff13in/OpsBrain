import test from 'node:test';
import assert from 'node:assert/strict';
import { createPersistence, accountPayload } from '../public/persistence.js';
import { CHAT_FIXTURES } from '../public/chat.js';
import { renderPage } from '../public/ui.js';
const ws='00000000-0000-4000-8000-000000000002',id='00000000-0000-4000-8000-000000000003';
const row={id,workspace_id:ws,title:'My project',version:1,updated_at:'2026-10-12T00:00:00Z'};
const reply=body=>({status:200,text:async()=>JSON.stringify(body)});

test('account payload preserves demo sources/outcomes and excludes transient/hidden fields',()=>{
 const payload=accountPayload([{question:'Why is this slow?',response:{...CHAT_FIXTURES.partial,hidden:'do not save'},pending:false}]);
 assert.equal(payload.mode,'demo');assert.deepEqual(payload.turns[0].response.sources,CHAT_FIXTURES.partial.sources);
 assert.ok(!JSON.stringify(payload).includes('do not save'));assert.equal(accountPayload([{question:'short',pending:true}]),null);
});
test('failed save retries the exact request id/body and refreshes persisted records',async()=>{
 const commands=[];let fail=true;
 const client=createPersistence({fetcher:async path=>reply({records:path.includes('/projects')?[row]:[],next_cursor:null}),
 sendMutation:async command=>{commands.push(structuredClone(command));return fail?{status:503}:{status:200,body:{id,version:1,deleted:false}};}});
 await client.load(ws);await client.save('project.create',id,0,{title:'My project'});
 assert.equal(client.snapshot().retry,true);fail=false;await client.retry();assert.deepEqual(commands[0],commands[1]);
 assert.equal(client.snapshot().projects[0].title,'My project');assert.match(client.snapshot().message,/saved/);
});
test('version conflicts are visible and do not silently overwrite records',async()=>{
 const client=createPersistence({fetcher:async()=>reply({records:[],next_cursor:null}),sendMutation:async()=>({status:409})});
 await client.load(ws);await client.save('project.update',id,1,{title:'New title'});
 assert.match(client.snapshot().message,/record changed/);assert.equal(client.snapshot().retry,false);
});
test('saved investigation reopens after constructing a new page controller',async()=>{
 const payload=accountPayload([{question:'Why is this slow?',response:CHAT_FIXTURES.ok}]);
 const client=createPersistence({fetcher:async path=>reply(path.endsWith('/'+id)?{...row,project_id:id,payload}:{records:[],next_cursor:null})});
 await client.load(ws);await client.open(id);assert.deepEqual(client.snapshot().selected.payload,payload);
 client.leave();assert.equal(client.snapshot().selected,null);
});
test('late reads after logout do not restore private saved work',async()=>{
 let finish;const client=createPersistence({fetcher:()=>new Promise(resolve=>{finish=resolve;})});
 const pending=client.open(id);client.leave();finish(reply({...row,payload:{mode:'demo',turns:[]}}));await pending;
 assert.equal(client.snapshot().selected,null);
});
test('write-enabled workspace renders explicit project deletion and profile preferences controls',()=>{
 const profile={display_name:'User',version:1,preferences:{default_section:'projects',reduced_motion:true}};
 const options={protectedState:{status:'authorized',workspaceId:ws,message:'Verified'},workspaceState:{status:'ready',workspaceId:ws,data:{workspace:{id:ws,name:'Workspace'},profile,recent_projects:[],capabilities:{project_writes:true,preferences:true,saved_work:true}}},
 persistenceState:{status:'ready',workspaceId:ws,projects:[row],saved:[],pending:false}};
 const projects=renderPage('workspace',{...options,workspaceSection:'projects'}).html;
 assert.match(projects,/id="project-create"/);assert.match(projects,/also deletes its saved investigations/);
 const settings=renderPage('workspace',{...options,workspaceSection:'settings'}).html;
 assert.match(settings,/id="profile-edit"/);assert.match(settings,/name="default_section"/);
});
