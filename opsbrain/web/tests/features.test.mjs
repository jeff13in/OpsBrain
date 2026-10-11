import test from 'node:test';
import assert from 'node:assert/strict';
import { renderPage } from '../public/ui.js';
import { CHAT_FIXTURES } from '../public/chat.js';

const chatState = { turns: [], pending: false, draft: 'Why is the website slow?', validation: '', scenario: 'ok' };
const liveConnection = { mode: 'live', pending: false, message: 'Orchestrator reachable. Agent availability is reported per request.', monitoring: null, sessionActive: true };

test('chat composers show a character counter that tracks the draft', () => {
  const demo = renderPage('chat', { chatState }).html;
  assert.match(demo, /id="chat-count"/);
  assert.match(demo, /24 \/ 2000/);
  const live = renderPage('chat', { chatState, connectionState: liveConnection }).html;
  assert.match(live, /id="chat-count"/);
  assert.match(live, /24 \/ 2000/);
});

test('history page has a filter control and reports the filtered total', () => {
  const records = [{ id: 'conv-1', mode: 'demo', createdAt: 1, updatedAt: 1, turns: [{ question: 'Why is the website slow?', response: CHAT_FIXTURES.partial }] }];
  const html = renderPage('history', { historyState: { records, persistent: true, warning: '', total: 2 }, historyFilter: 'website' }).html;
  assert.match(html, /id="history-filter"/);
  assert.match(html, /type="search"/);
  assert.match(html, /value="website"/);
  assert.match(html, /Filters this list only/);
  assert.match(html, /1 of 2 \/ 20/);
  const unfiltered = renderPage('history', { historyState: { records, persistent: true, warning: '' } }).html;
  assert.match(unfiltered, /1 \/ 20/);
  assert.doesNotMatch(unfiltered, /of 2/);
});

test('live overview shows connection status and session state without inventing health', () => {
  const html = renderPage('dashboard', { connectionState: liveConnection }).html;
  assert.match(html, /API connection/);
  assert.match(html, /Orchestrator reachable/);
  assert.match(html, /Active on this page/);
  assert.match(html, /badge-live/);
  assert.doesNotMatch(html, /All systems/);
  const failed = renderPage('dashboard', { connectionState: { mode: 'disconnected', pending: false, message: 'Connection failed.', monitoring: null, sessionActive: false } }).html;
  assert.match(failed, /Connection failed/);
  assert.match(failed, /No active session/);
  assert.doesNotMatch(failed, /badge-live/);
});

test('monitoring error state offers a reset and still shows no charts', () => {
  const html = renderPage('monitoring', { monitoringState: { scenario: 'error', range: '15m', pending: false, samples: null, refreshedAt: null, auto: false } }).html;
  assert.match(html, /id="monitoring-reset"/);
  assert.match(html, /Reset demo preview/);
  assert.doesNotMatch(html, /<polyline/);
});

test('filter and counter text is escaped', () => {
  const html = renderPage('history', { historyState: { records: [], persistent: true, warning: '' }, historyFilter: '"><script>' }).html;
  assert.doesNotMatch(html, /value=""><script>/);
  assert.match(html, /&quot;&gt;&lt;script&gt;/);
});
