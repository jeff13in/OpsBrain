import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { request as httpRequest, createServer } from 'node:http';
import { createApi, validateAnswer } from '../public/api.js';
import { createChat, CHAT_FIXTURES } from '../public/chat.js';
import { renderPage } from '../public/ui.js';
import { createGateway } from '../scripts/gateway.mjs';
import { createPreviewServer } from '../scripts/server.mjs';
import { createHistory } from '../public/history.js';

const answer = (status = 'ok') => ({ ...structuredClone(CHAT_FIXTURES[status]), request_id: 'request-1', question: 'Valid question' });
const response = (body, status = 200) => new Response(JSON.stringify(body), { status });
const health = { agent: 'orchestrator', status: 'ok' };

test('API retains validated routing and latency and renders them safely', () => {
  const body = answer();
  body.routing = { agents: body.results.map(item => item.agent), method: 'keyword', reason: '<img src=x onerror=alert(1)>' };
  body.results[0].latency_ms = 42;
  const result = validateAnswer(body, 'Valid question');
  assert.equal(result.results[0].latency_ms, 42);
  assert.deepEqual(result.routing, body.routing);
  const html = renderPage('chat', { chatState: { turns: [{ question: 'Valid question', response: result, mode: 'live' }], draft: '', scenario: 'ok' } }).html;
  assert.match(html, /Routing: keyword/);
  assert.match(html, /Latency: 42 ms/);
  assert.doesNotMatch(html, /<img/);
  for (const routing of [{ ...body.routing, agents: ['rag'] }, { ...body.routing, method: 'unsafe' }]) {
    assert.throws(() => validateAnswer({ ...body, routing }, 'Valid question'));
  }
  body.results[0].latency_ms = -1;
  assert.throws(() => validateAnswer(body, 'Valid question'));
});

test('late live answers cannot survive a disconnect even when the transport ignores abort', async () => {
  let complete;
  const api = createApi({ request: path => path.endsWith('/health') ? Promise.resolve(response(health)) : new Promise(resolve => { complete = resolve; }) });
  await api.connect();
  const pending = api.ask('Valid question');
  api.disconnect();
  complete(response(answer()));
  await assert.rejects(pending, /superseded/);
});

test('API stays demo until explicit health success and forwards questions with a session', async () => {
  const calls = [];
  const api = createApi({ sessionId: () => 'session-1', request: async (path, options) => {
    calls.push({ path, options });
    return response(path.endsWith('/health') ? health : answer('partial'));
  } });
  assert.equal(api.snapshot().mode, 'demo');
  assert.equal(calls.length, 0);
  await api.connect();
  assert.equal(api.snapshot().mode, 'live');
  const result = await api.ask('Valid question');
  assert.equal(result.status, 'partial');
  assert.deepEqual(JSON.parse(calls[1].options.body), { question: 'Valid question', session_id: 'session-1' });
  assert.equal(calls[1].options.credentials, 'omit');
  api.disconnect();
  assert.equal(calls[1].options.signal.aborted, true);
  await assert.rejects(api.ask('Valid question'));
});

test('health failure and cancelled checks cannot silently become live or demo', async () => {
  let complete;
  const api = createApi({ request: () => new Promise(resolve => { complete = resolve; }) });
  const pending = api.connect();
  api.disconnect('demo');
  complete(response(health));
  assert.equal(await pending, false);
  assert.equal(api.snapshot().mode, 'demo');
  const failure = createApi({ request: async () => response({ error: 'private error' }, 503) });
  assert.equal(await failure.connect(), false);
  assert.equal(failure.snapshot().mode, 'disconnected');
  assert.match(failure.snapshot().message, /No demo fallback/);
});

test('answer schema rejects malformed or inconsistent successes and preserves structured 502', async () => {
  assert.equal(validateAnswer(answer('partial'), 'Valid question').status, 'partial');
  for (const bad of [null, { ...answer(), results: [] }, { ...answer(), question: 'Wrong question' }, { ...answer(), status: 'partial' }, { ...answer(), sources: ['invented'] }, { ...answer(), results: [...answer().results, answer().results[0]] }]) {
    assert.throws(() => validateAnswer(bad, 'Valid question'));
  }
  const api = createApi({ sessionId: () => 'session', request: async path => response(path.endsWith('/health') ? health : answer('error'), path.endsWith('/health') ? 200 : 502) });
  await api.connect();
  assert.equal((await api.ask('Valid question')).status, 'error');
});

test('live chat failure never calls demo reply and mode changes discard pending answers', async () => {
  const chat = createChat({ reply: async () => { throw new Error('failure'); } });
  chat.setMode('live');
  await chat.submit('Valid question');
  assert.match(chat.snapshot().turns[0].response.answer, /No demo fallback/);
  assert.deepEqual(chat.snapshot().turns[0].response.sources, []);
  let complete;
  const pendingChat = createChat({ reply: () => new Promise(resolve => { complete = resolve; }) });
  pendingChat.setMode('live');
  const pending = pendingChat.submit('Valid question');
  pendingChat.setMode('demo');
  complete(answer());
  assert.equal(await pending, false);
  assert.deepEqual(pendingChat.snapshot().turns, []);
});

test('monitoring retains partial successful snapshots and validates missing or malformed data', async () => {
  const api = createApi({ sessionId: () => 'session', request: async path => {
    if (path.endsWith('/health') && path.includes('orchestrator')) return response(health);
    if (path.includes('alerts')) return response({ total: 3, active: 2, suppressed: 1 });
    return response({ total_pods: -1, status_breakdown: {}, pods: [] });
  } });
  await api.connect();
  await api.refreshMonitoring();
  assert.equal(api.snapshot().monitoring.alerts.active, 2);
  assert.equal(api.snapshot().monitoring.pods, null);
  const html = renderPage('monitoring', { connectionState: api.snapshot() }).html;
  assert.match(html, /Pod health unavailable/);
  assert.doesNotMatch(html, /<polyline|synthetic samples/);
});

test('live rendering escapes sources and never labels live results synthetic', () => {
  const body = answer();
  body.answer = '<img src=x> [1]';
  const html = renderPage('chat', { connectionState: { mode: 'live' }, chatState: { mode: 'live', turns: [{ question: '<script>', response: body, mode: 'live' }], draft: '', pending: false, validation: '' } }).html;
  assert.match(html, /Live · Complete/);
  assert.match(html, /API SOURCE/);
  assert.doesNotMatch(html, /<img|<script>|SYNTHETIC SOURCE|Example answer/);
});

test('gateway rejects non-loopback origins and exposes only read/query routes', async () => {
  for (const url of ['https://example.com', 'http://localhost:8000', 'http://user:pass@127.0.0.1:8000', 'http://127.0.0.1:8000/private']) {
    assert.throws(() => createGateway({ orchestrator: url }));
  }
  const calls = [];
  const gateway = createGateway({ orchestrator: 'http://127.0.0.1:8000', monitoring: 'http://127.0.0.1:8002', request: async (path, options) => {
    calls.push({ path, options }); return response(path.endsWith('/health') ? health : answer('partial'));
  } });
  const server = createPreviewServer(undefined, { gateway });
  server.listen(0, '127.0.0.1');
  try {
    await once(server, 'listening');
    const origin = `http://127.0.0.1:${server.address().port}`;
    const healthy = await fetch(origin + '/api/orchestrator/health');
    assert.equal(healthy.status, 200);
    assert.match(healthy.headers.get('content-security-policy'), /connect-src 'self'/);
    const asked = await fetch(origin + '/api/orchestrator/ask', { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: origin, Authorization: 'must-not-forward' }, body: JSON.stringify({ question: 'Valid question' }) });
    assert.equal(asked.status, 200);
    assert.equal(calls[1].options.headers.Authorization, undefined);
    assert.deepEqual(JSON.parse(calls[1].options.body), { question: 'Valid question' });
    const before = calls.length;
    for (const [path, options, expected] of [
      ['/api/orchestrator/ask', { method: 'DELETE' }, 405],
      ['/api/orchestrator/ask', { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'https://evil.example' }, body: '{}' }, 403],
      ['/api/orchestrator/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: 'Valid question', action: 'apply' }) }, 400],
      ['/api/monitoring/apply', {}, 404],
      ['/api/orchestrator/health?url=http://example.com', {}, 404],
    ]) assert.equal((await fetch(origin + path, options)).status, expected, path);
    const hostileHost = await new Promise((resolve, reject) => {
      const req = httpRequest(origin + '/api/orchestrator/health', { headers: { Host: 'evil.example' } }, res => {
        res.resume(); resolve(res.statusCode);
      });
      req.on('error', reject); req.end();
    });
    assert.equal(hostileHost, 403);
    assert.equal(calls.length, before);
  } finally { await new Promise(resolve => server.close(resolve)); }
});

test('real local HTTP path connects adapter, gateway and a contract-compatible backend', async () => {
  const backend = createServer(async (req, res) => {
    const body = req.url === '/health' ? health : req.url === '/alerts/summary' ? { total: 1, active: 1, suppressed: 0 }
      : req.url === '/pods/health' ? { total_pods: 2, status_breakdown: { Running: 2 }, pods: [] } : answer('partial');
    if (req.url === '/ask') {
      const chunks = []; for await (const chunk of req) chunks.push(chunk);
      assert.equal(JSON.parse(Buffer.concat(chunks)).question, 'Valid question');
    }
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(body));
  });
  backend.listen(0, '127.0.0.1');
  await once(backend, 'listening');
  const upstream = `http://127.0.0.1:${backend.address().port}`;
  const preview = createPreviewServer(undefined, { gateway: createGateway({ orchestrator: upstream, monitoring: upstream }) });
  preview.listen(0, '127.0.0.1');
  try {
    await once(preview, 'listening');
    const origin = `http://127.0.0.1:${preview.address().port}`;
    const api = createApi({ sessionId: () => 'session-1', request: (path, options) => fetch(origin + path, options) });
    assert.equal(await api.connect(), true);
    assert.equal((await api.ask('Valid question')).status, 'partial');
    await api.refreshMonitoring();
    assert.equal(api.snapshot().monitoring.alerts.active, 1);
    assert.equal(api.snapshot().monitoring.pods.total, 2);
    api.disconnect('demo');
    assert.equal(api.snapshot().monitoring, null);
  } finally {
    await Promise.all([new Promise(resolve => preview.close(resolve)), new Promise(resolve => backend.close(resolve))]);
  }
});

test('live turns cannot be saved as demo history', () => {
  const store = createHistory({ storage: () => ({ getItem: () => null, setItem() {} }), id: () => 'record-1' });
  assert.equal(store.save(null, [{ question: 'Valid question', mode: 'live', response: answer() }]), null);
  assert.deepEqual(store.snapshot().records, []);
});
