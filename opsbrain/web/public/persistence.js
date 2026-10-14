const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const text = (v, max) => typeof v === 'string' && v.length <= max;
export function accountPayload(turns) {
  if (!Array.isArray(turns) || !turns.length || turns.length > 20) return null;
  const clean = [];
  for (const turn of turns) {
    if (turn?.mode === 'live') return null; // Live storage awaits tenant/retention acceptance.
    const r = turn?.response;
    if (turn.pending || !text(turn.question,2000) || turn.question.trim().length<5 || !r || !['ok','partial','error'].includes(r.status)
      || !text(r.answer,20000) || !Array.isArray(r.sources) || r.sources.length>20 || !r.sources.every(s=>text(s,2000))
      || !Array.isArray(r.results) || r.results.length>4) return null;
    const results=[];
    for(const item of r.results){
      if(!['rag','monitoring','infra','code'].includes(item.agent)||!['ok','error','timeout'].includes(item.status)
       || !(item.answer===null||text(item.answer,20000)) || !Array.isArray(item.sources)||item.sources.length>20||!item.sources.every(s=>text(s,2000))
       || !(item.error===null||(text(item.error?.code,100)&&text(item.error?.message,2000)))) return null;
      results.push({agent:item.agent,status:item.status,answer:item.answer,sources:[...item.sources],error:item.error?{code:item.error.code,message:item.error.message}:null});
    }
    clean.push({question:turn.question,response:{status:r.status,answer:r.answer,sources:[...r.sources],results}});
  }
  const payload={mode:'demo',turns:clean};
  return new TextEncoder().encode(JSON.stringify(payload)).length<=131072?payload:null;
}
function validRow(row,ws){return row&&uuid.test(row.id)&&row.workspace_id===ws&&text(row.title,200)&&row.title.trim()
 && Number.isSafeInteger(row.version)&&row.version>0&&text(row.updated_at,64)&&Number.isFinite(Date.parse(row.updated_at));}

export function createPersistence({fetcher=(...args)=>globalThis.fetch(...args),sendMutation,onChange=()=>{},onSaved=()=>{},timeoutMs=10000}={}){
 let state={workspaceId:null,status:'idle',projects:[],saved:[],selected:null,pending:false,message:'',retry:false,nextProjects:null,nextSaved:null};
 let generation=0,lastCommand=null,controllers=new Set();
 const snapshot=()=>structuredClone(state);
 function leave(){generation++;for(const c of controllers)c.abort();controllers.clear();lastCommand=null;
 state={workspaceId:null,status:'idle',projects:[],saved:[],selected:null,pending:false,message:'',retry:false,nextProjects:null,nextSaved:null};}
 async function read(path){const c=new AbortController();controllers.add(c);const t=setTimeout(()=>c.abort(),timeoutMs);
 try{const response=await fetcher(path,{credentials:'same-origin',cache:'no-store',redirect:'error',signal:c.signal});
 if(response.status!==200)throw new Error('Read unavailable');const body=await response.text();if(body.length>262144)throw new Error('Oversized read');return JSON.parse(body);
 }finally{clearTimeout(t);controllers.delete(c);}}
 async function load(ws){leave();if(!uuid.test(ws))return;const current=generation;state.workspaceId=ws;state.status='loading';onChange();
 try{const [projects,saved]=await Promise.all(['projects','saved_work'].map(kind=>read(`/api/workspaces/${ws}/records/${kind}`)));
 for(const page of [projects,saved]){if(!Array.isArray(page.records)||page.records.length>20||!page.records.every(r=>validRow(r,ws))||!(page.next_cursor===null||uuid.test(page.next_cursor)))throw new Error('Invalid page');}
 if(current!==generation)return;state={...state,status:'ready',projects:projects.records,saved:saved.records,nextProjects:projects.next_cursor,nextSaved:saved.next_cursor};
 }catch{if(current===generation){state.status='error';state.message='Account records could not be loaded. Please retry.';}}
 if(current===generation)onChange();}
 async function more(kind){const cursor=kind==='projects'?state.nextProjects:state.nextSaved;if(!cursor||state.pending)return;
 const current=generation;state.pending=true;onChange();try{const page=await read(`/api/workspaces/${state.workspaceId}/records/${kind}?cursor=${cursor}`);
 if(current!==generation)return;if(!Array.isArray(page.records)||page.records.length>20||!page.records.every(r=>validRow(r,state.workspaceId))||!(page.next_cursor===null||uuid.test(page.next_cursor)))throw new Error('Invalid page');
 const field=kind==='projects'?'projects':'saved';state[field]=[...new Map([...state[field],...page.records].map(r=>[r.id,r])).values()];state[kind==='projects'?'nextProjects':'nextSaved']=page.next_cursor;
 }catch{if(current===generation)state.message='More records could not be loaded.';}finally{if(current===generation){state.pending=false;onChange();}}}
 async function open(id){if(!uuid.test(id))return;const current=generation;state.selected=null;state.pending=true;onChange();
 try{const row=await read(`/api/workspaces/${state.workspaceId}/records/saved_work/${id}`);
 if(current!==generation)return;if(!validRow(row,state.workspaceId)||row.payload?.mode!=='demo'||!accountPayload(row.payload.turns))throw new Error('Invalid saved work');
 state.selected={...row,payload:accountPayload(row.payload.turns)};state.message='Saved investigation reopened.';
 }catch{if(current===generation)state.message='Saved work could not be opened.';}finally{if(current===generation){state.pending=false;onChange();}}}
 async function run(command){if(state.pending||!state.workspaceId)return;const current=generation;lastCommand=structuredClone(command);state.pending=true;state.retry=false;state.message='Saving account changes…';onChange();
 try{const {status,body}=await sendMutation(lastCommand);if(current!==generation)return;
 if(status!==200||!body||!uuid.test(body.id)||!Number.isSafeInteger(body.version)){
 state.message=({409:'This record changed. Reload before editing.',404:'This record is no longer available.',429:'Workspace storage limit reached.',422:'Check the record fields and size.'})[status]||'Save failed. You can retry the same request.';state.retry=![409,404,422,429].includes(status);return;}
 const ws=state.workspaceId,reloadGeneration=generation+1;await load(ws);if(generation!==reloadGeneration)return;
 state.message=state.status==='ready'?'Account changes saved.':'Changes saved; account records could not be reloaded.';onChange();await onSaved();
 }catch{if(current===generation){state.message='Save failed. You can retry the same request.';state.retry=true;}}
 finally{if(current===generation){state.pending=false;onChange();}}}
 async function save(operation,id,version,changes){return run({request_id:crypto.randomUUID(),operation,record_id:id,expected_version:version,changes});}
 return {snapshot,load,leave,more,open,save,retry:()=>lastCommand?run(lastCommand):undefined};
}
