import test from 'node:test';
import assert from 'node:assert/strict';
import { CHAT_FIXTURES } from '../public/chat.js';
import { canExportInvestigation, investigationReport, downloadInvestigation } from '../public/investigation.js';
import { openSourceTarget, sourcePassage } from '../public/sources.js';
import { chatResponse, renderPage } from '../public/ui.js';

const state = (response = CHAT_FIXTURES.partial, mode = 'demo') => ({ mode, pending: false, draft: '', validation: '', scenario: 'ok', turns: [{ question: 'Why is the website slow?', mode, response }] });

test('export preserves partial outcomes, source order, routing and latency with truthful provenance', () => {
  const response = structuredClone(CHAT_FIXTURES.partial);
  response.routing = { method: 'keyword', reason: 'CPU context', agents: ['rag', 'monitoring', 'infra', 'code'] };
  response.results[0].latency_ms = 23;
  response.hidden_context = 'private hidden model context';
  const report = investigationReport(state(response, 'live'));
  assert.equal(report.filename, 'opsbrain-investigation-live.md');
  for (const text of ['Provenance: Live', 'Outcome: partial', 'Outcome: error', 'Latency: 23 ms', 'Method: keyword', 'CPU context', response.sources[0], 'Synthetic dependency unavailable']) assert.ok(report.content.includes(text), text);
  assert.doesNotMatch(report.content, /private hidden model context/);
  assert.equal(investigationReport(state()).content, investigationReport(state()).content);
  assert.match(investigationReport(state()).content, /Demo results are synthetic/);
  assert.match(investigationReport(state(CHAT_FIXTURES.error)).content, /No sources available/);
});

test('empty, pending, incomplete and invalid reports cannot export', () => {
  for (const invalid of [null, {}, { turns: [] }, { ...state(), pending: true }, state(null), state({ ...CHAT_FIXTURES.ok, sources: ['a'.repeat(2001)] }), state(CHAT_FIXTURES.ok, 'unknown'), { ...state(), turns: Array(21).fill(state().turns[0]) }]) {
    assert.equal(canExportInvestigation(invalid), false);
    assert.throws(() => investigationReport(invalid));
  }
});

test('Unicode, multiline HTML, URLs and embedded Markdown fences stay inside literal blocks', () => {
  const hostile = '诊断 🧠\r\n```\n<script>alert(1)</script>\n[open](javascript:alert(1))\nhttps://example.com\n``````\n# injected heading';
  const value = state(); value.turns[0].question = hostile;
  const report = investigationReport(value);
  assert.ok(report.content.includes('```````text\n' + hostile.replace(/\r\n/g, '\n') + '\n```````'));
  assert.doesNotMatch(report.content, /\r/);
  let fence = null;
  for (const line of report.content.split('\n')) {
    if (!fence && /^`{3,}text$/.test(line)) fence = line.slice(0, -4);
    else if (fence && line === fence) fence = null;
    else if (!fence) assert.doesNotMatch(line, /<script>|javascript:|https:\/\/|injected heading/);
  }
  assert.equal(fence, null);
});

test('multibyte output is capped by bytes', () => {
  const response = structuredClone(CHAT_FIXTURES.ok);
  response.answer = '界'.repeat(20000);
  response.results.forEach(result => { result.answer = response.answer; });
  const value = state(response); value.turns = Array(20).fill(value.turns[0]);
  assert.throws(() => investigationReport(value), /size limit/);
});

test('local download uses a fixed filename, removes the anchor and revokes the object URL', async () => {
  let blob, cleanup, clicked = false, removed = false;
  const link = { click() { clicked = true; }, remove() { removed = true; } };
  const doc = { createElement(tag) { assert.equal(tag, 'a'); return link; }, body: { append(value) { assert.equal(value, link); } } };
  const urls = { createObjectURL(value) { blob = value; return 'blob:local'; }, revokeObjectURL(value) { assert.equal(value, 'blob:local'); cleanup = 'revoked'; } };
  downloadInvestigation(state(), { document: doc, urls, defer(fn, delay) { assert.equal(delay, 30000); cleanup = fn; } });
  assert.equal(clicked, true); assert.equal(removed, true); assert.equal(link.hidden, true);
  assert.equal(link.download, 'opsbrain-investigation-demo.md');
  assert.equal(blob.type, 'text/markdown;charset=utf-8');
  assert.match(await blob.text(), /Provenance: Demo/);
  cleanup(); assert.equal(cleanup, 'revoked');
  const before = clicked; assert.throws(() => downloadInvestigation({ turns: [] }, { document: doc, urls })); assert.equal(clicked, before);
});

test('report controls disable empty and pending chats and enable complete Demo and Live chats', () => {
  for (const mode of ['demo', 'live']) {
    const options = { chatState: state(CHAT_FIXTURES.ok, mode), connectionState: { mode } };
    assert.match(renderPage('chat', options).html, /id="export-investigation">Download/);
    options.chatState.pending = true;
    assert.match(renderPage('chat', options).html, /id="export-investigation" disabled/);
  }
  assert.match(renderPage('chat').html, /id="export-investigation" disabled/);
});

test('passages are explicit synthetic fixtures; live and hostile IDs never resolve a passage', () => {
  const source = 'Example runbook: service latency';
  assert.equal(sourcePassage(source, 'demo').available, true);
  assert.match(sourcePassage(source, 'demo').provenance, /Synthetic/);
  assert.equal(sourcePassage(source, 'live').available, false);
  for (const hostile of ['__proto__', 'constructor', '../../.env', 'https://example.com', '<img src=x onerror=alert(1)>']) {
    assert.equal(sourcePassage(hostile, 'demo').available, false);
    assert.equal(sourcePassage(hostile, 'live').available, false);
  }
  const html = chatResponse(CHAT_FIXTURES.ok, 0, 'live');
  assert.match(html, /Passage unavailable/);
  assert.doesNotMatch(html, /Synthetic runbook passage/);
  assert.match(chatResponse(CHAT_FIXTURES.ok, 0), /Read example passage/);
});

test('citation selection opens inline passage and focuses its existing source target', () => {
  const detail = { open: false };
  let scrolled = false, focused = false;
  openSourceTarget({ querySelector(selector) { assert.equal(selector, 'details'); return detail; }, scrollIntoView() { scrolled = true; }, focus(options) { assert.deepEqual(options, { preventScroll: true }); focused = true; } });
  assert.equal(detail.open, true); assert.equal(scrolled, true); assert.equal(focused, true);
  openSourceTarget(null);
});

test('account saved-report control is gated by workspace authorization and disabled during mutations', () => {
  const workspaceId = '00000000-0000-4000-8000-000000000002';
  const options = { workspaceSection: 'projects', protectedState: { status: 'authorized', workspaceId, message: 'Verified' },
    workspaceState: { status: 'ready', workspaceId, data: { workspace: { id: workspaceId, name: 'Workspace' }, profile: {}, recent_projects: [], capabilities: { project_writes: true } } },
    persistenceState: { status: 'ready', workspaceId, projects: [], saved: [], pending: false, selected: { id: 'saved', title: 'Saved report', payload: { mode: 'demo', turns: state().turns } } } };
  assert.match(renderPage('workspace', options).html, /id="export-saved-investigation">Download/);
  options.persistenceState.pending = true;
  assert.match(renderPage('workspace', options).html, /id="export-saved-investigation" disabled/);
  options.protectedState.status = 'anonymous';
  assert.doesNotMatch(renderPage('workspace', options).html, /export-saved-investigation|Saved report/);
});
