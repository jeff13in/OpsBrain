import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { operational, normalizeSeries, presets } from '../scripts/operational.mjs';
import { createGateway } from '../scripts/gateway.mjs';
import { createPreviewServer } from '../scripts/server.mjs';
import { createApi } from '../public/api.js';
import { renderPage, metricChart } from '../public/ui.js';
import { METRICS } from '../public/monitoring.js';
import { accountPayload } from '../public/persistence.js';
const end = 1800000000, clock = () => end * 1000;
const reply = body => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
const health = { status:'ok', agent:'orchestrator' };
const upstream = 'http://127.0.0.1:9000';
const matrix = {result_type:'matrix',result:[{values:[[end-120,'5'],[end-60,'6']]}]};

test('aggregate health never reveals health metadata or infers dependency readiness', async () => {
  const data = await operational('/api/status', new URL('http://local/api/status'), {orchestrator:upstream,rag:upstream,monitoring:upstream},
    async () => reply({...health,services:{secret:'private-upstream'}}), new AbortController().signal, clock);
  assert.equal(data.services.length, 5);
  assert.ok(data.services.every(row => row.readiness === 'unknown'));
  assert.equal(data.services.find(row => row.service==='code').reachability, 'unconfigured');
  assert.doesNotMatch(JSON.stringify(data), /private-upstream|secret/);
});

test('series use only fixed queries and preserve partial unavailable metrics', async () => {
  const calls=[];
  const data=await operational('/api/monitoring/series',new URL('http://local/api/monitoring/series?range=15m'),{monitoring:upstream},async (url,options)=>{
    const body=JSON.parse(options.body);calls.push(body);
    return reply(body.query===presets.errors?{result_type:'matrix',result:[]}:matrix);
  },new AbortController().signal,clock);
  assert.equal(calls.length,6);
  assert.ok(calls.every(body=>Object.values(presets).includes(body.query)&&body.step==='60s'));
  assert.equal(data.metrics.cpu.points[1].observedAt,new Date((end-60)*1000).toISOString());
  assert.deepEqual(data.metrics.errors,{status:'unavailable',points:[]});
  await assert.rejects(operational('/api/monitoring/series',new URL('http://local/?range=2d'),{},()=>{},new AbortController().signal,clock));
});

test('series reject invalid order, bounds, NaN, excessive series and samples',()=>{
  for(const values of [[[end,'NaN']],[[end,'']],[[end+1,'1']],[[end,'1'],[end-1,'2']],Array.from({length:62},(_,i)=>[end-62+i,'1'])])
    assert.throws(()=>normalizeSeries({result_type:'matrix',result:[{values}]},end-900,end));
  assert.throws(()=>normalizeSeries({result_type:'matrix',result:[{},{}]},end-900,end));
});

test('oversized health and timed-out metric requests return safe unavailable states',async()=>{
  const large=await operational('/api/status',new URL('http://local/'),{rag:upstream},async()=>reply({status:'ok',private:'x'.repeat(200001)}),new AbortController().signal,clock);
  assert.equal(large.services.find(row=>row.service==='rag').reachability,'unavailable');
  const data=await operational('/api/monitoring/series',new URL('http://local/?range=1h'),{monitoring:upstream},async (url,options)=>{
    assert.equal(options.redirect,'error');throw new Error('Timeout: private details');
  },new AbortController().signal,clock);
  assert.ok(Object.values(data.metrics).every(row=>row.status==='unavailable'&&row.points.length===0));
  assert.doesNotMatch(JSON.stringify(data),/private details/);
});

test('new gateway endpoints enforce local origin and reject arbitrary query/preset inputs',async()=>{
  let calls=0;
  const server=createPreviewServer(undefined,{gateway:createGateway({orchestrator:upstream,request:async()=>{calls++;return reply(health);}})});
  server.listen(0,'127.0.0.1');await once(server,'listening');
  const origin=`http://127.0.0.1:${server.address().port}`;
  try{
    const response=await fetch(origin+'/api/status');assert.equal(response.status,200);
    assert.equal((await response.json()).services.length,5);
    for(const path of ['/api/status?target=evil','/api/monitoring/series?range=15m&query=up','/api/monitoring/series?range=15m&range=1h'])
      assert.equal((await fetch(origin+path)).status,400);
    assert.equal((await fetch(origin+'/api/status',{headers:{Origin:'https://evil.example'}})).status,403);
    assert.equal(calls,1);
  }finally{await new Promise(resolve=>server.close(resolve));}
});

test('client readiness marks retained failures stale and rejects cancelled late results',async()=>{
  let bad=false,finish;
  const status=await operational('/api/status',new URL('http://local/'),{},()=>{},new AbortController().signal,clock);
  const api=createApi({request:async path=>path.endsWith('/health')?reply(health):bad?new Promise(resolve=>{finish=resolve;}):reply(status)});
  await api.connect();await api.refreshStatus();
  assert.equal(api.snapshot().readiness.services.length,5);
  bad=true;const pending=api.refreshStatus();api.leaveOperational();finish(reply(status));await pending;
  assert.equal(api.snapshot().statusPending,false);
  assert.equal(api.snapshot().readiness.stale,false);
  const failure=api.refreshStatus();finish(new Response('{}',{status:503}));await failure;
  assert.equal(api.snapshot().readiness.stale,true);
});

test('live chart client validates points, retains stale failures and renders API provenance',async()=>{
  const data=await operational('/api/monitoring/series',new URL('http://local/?range=15m'),{monitoring:upstream},async()=>reply(matrix),new AbortController().signal,clock);
  let fail=false;
  const api=createApi({request:async path=>path.endsWith('/health')?reply(health):fail?reply({...data,metrics:{}}):reply(data)});
  await api.connect();await api.refreshSeries();
  const html=renderPage('monitoring',{connectionState:api.snapshot()}).html;
  assert.match(html,/Observation time \(UTC\)/);assert.match(html,/Latest API sample/);
  assert.doesNotMatch(html,/synthetic samples|Latest synthetic/);
  fail=true;await api.refreshSeries();assert.equal(api.snapshot().series.stale,true);
  api.disconnect();assert.equal(api.snapshot().series,undefined);
});

test('live charts permit counts beyond demo scale and leave missing metric unavailable',()=>{
  const html=metricChart(METRICS.find(row=>row.id==='requests'),[{minutesAgo:2,value:1000,observedAt:'a'},{minutesAgo:1,value:1100,observedAt:'b'}],'live');
  assert.match(html,/<polyline/);assert.match(html,/1100/);
  assert.match(metricChart(METRICS[0],[],'live'),/Metric unavailable/);
  const gaps=metricChart(METRICS[0],[{minutesAgo:5,value:10},{minutesAgo:4,value:11},{minutesAgo:1,value:12},{minutesAgo:0,value:13}],'live');
  assert.equal((gaps.match(/<polyline/g)||[]).length,2);
});

test('account Demo persistence cannot relabel a Live conversation',()=>{
  assert.equal(accountPayload([{mode:'live',question:'Valid question',response:{status:'error',answer:'Unavailable',sources:[],results:[]}}]),null);
});
