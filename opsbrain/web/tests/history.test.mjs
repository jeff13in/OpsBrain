import test from 'node:test';
import assert from 'node:assert/strict';
import { createHistory, HISTORY_KEY, HISTORY_TTL } from '../public/history.js';
import { CHAT_FIXTURES, createChat } from '../public/chat.js';
import { renderPage } from '../public/ui.js';

function setup() {
  const values = new Map();
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  let time = 1000000;
  let sequence = 0;
  const options = { storage: () => storage, now: () => time, id: () => `conversation-${++sequence}` };
  return { values, storage, options, history: createHistory(options), advance: duration => { time += duration; } };
}
const turns = question => [{ question, response: CHAT_FIXTURES.partial }];

test('message updates extend retention; opening and unchanged saves do not', () => {
  const env = setup();
  const id = env.history.save(null, turns('Why is the website slow?'));
  env.advance(HISTORY_TTL - 1);
  const fresh = createHistory(env.options);
  assert.equal(fresh.get(id).turns[0].response.status, 'partial');
  const created = fresh.get(id).createdAt;
  assert.equal(fresh.save(id, [...turns('Why is the website slow?'), ...turns('What should I inspect next?')]), id);
  assert.equal(fresh.get(id).createdAt, created);
  env.advance(1);
  assert.ok(fresh.get(id));
  const updated = fresh.get(id).updatedAt;
  assert.equal(fresh.save(id, fresh.get(id).turns), id);
  assert.equal(fresh.get(id).updatedAt, updated);
  env.advance(HISTORY_TTL - 1);
  assert.equal(fresh.get(id), null);
  assert.deepEqual(JSON.parse(env.values.get(HISTORY_KEY)).records, []);
  assert.equal(fresh.save(id, turns('Expired conversation question')), null);
});

test('deletion and clearing affect only the owned history key', () => {
  const env = setup();
  env.values.set('other-app', 'keep me');
  const first = env.history.save(null, turns('First question'));
  const second = env.history.save(null, turns('Second question'));
  env.history.remove(first);
  assert.equal(createHistory(env.options).get(first), null);
  assert.ok(env.history.get(second));
  env.history.clear();
  assert.deepEqual(createHistory(env.options).snapshot().records, []);
  assert.equal(env.values.get('other-app'), 'keep me');
});

test('history keeps latest twenty conversations and excludes unfinished turns', () => {
  const env = setup();
  assert.equal(env.history.save(null, [{ question: 'Pending question', response: null }]), null);
  for (let i = 0; i < 21; i++) { env.advance(1); env.history.save(null, turns(`Question ${i}`)); }
  const records = env.history.snapshot().records;
  assert.equal(records.length, 20);
  assert.equal(records[0].turns[0].question, 'Question 20');
  assert.equal(records.at(-1).turns[0].question, 'Question 1');
});

test('storage denial and quota failure preserve memory with an explicit warning', () => {
  for (const options of [
    { storage: () => { throw new Error('Access denied'); } },
    { storage: () => ({ getItem: () => null, setItem: () => { throw new Error('Quota'); } }) },
  ]) {
    const history = createHistory({ ...options, now: () => 100, id: () => 'demo-1' });
    const id = history.save(null, turns('Valid question'));
    assert.ok(history.get(id));
    assert.equal(history.snapshot().persistent, false);
    assert.match(history.snapshot().warning, /page memory/);
    history.remove(id);
    assert.equal(history.get(id), null);
  }
});

test('malformed, future-dated, oversized and invalid history cannot crash rendering', () => {
  const env = setup();
  for (const value of ['{broken', JSON.stringify({ version: 7, records: [] }), 'x'.repeat(1000001)]) {
    env.values.set(HISTORY_KEY, value);
    const state = createHistory(env.options).snapshot();
    assert.deepEqual(state.records, []);
    assert.match(state.warning, /Invalid/);
    assert.doesNotThrow(() => renderPage('history', { historyState: state }));
  }
  const id = env.history.save(null, turns('Valid question'));
  const record = env.history.get(id);
  for (const invalid of [
    { ...record, createdAt: 999999999 },
    { ...record, mode: 'live' },
    { ...record, turns: [{ question: 'Valid question', response: { status: 'ok', sources: 'bad' } }] },
    { ...record, id: '\"><script>' },
  ]) {
    env.values.set(HISTORY_KEY, JSON.stringify({ version: 1, records: [invalid] }));
    assert.deepEqual(createHistory(env.options).snapshot().records, []);
  }
});

test('stored text stays escaped and restored answers preserve citation and failure context', () => {
  const env = setup();
  const question = '<img src=x onerror="alert(1)">';
  const id = env.history.save(null, turns(question));
  const historyHTML = renderPage('history', { historyState: env.history.snapshot() }).html;
  assert.doesNotMatch(historyHTML, /<img/);
  assert.match(historyHTML, /&lt;img/);
  assert.match(historyHTML, /data-open-history=/);
  const chat = createChat();
  chat.restore(env.history.get(id).turns);
  const html = renderPage('chat', { chatState: chat.snapshot(), historyState: env.history.snapshot() }).html;
  assert.match(html, /Partial availability/);
  assert.match(html, /data-source-target=/);
  assert.match(html, /Sample unavailable/);
  assert.doesNotMatch(html, /<img/);
});

test('restoring a saved conversation cancels a pending demo completion', async () => {
  let complete;
  const chat = createChat({ reply: () => new Promise(resolve => { complete = resolve; }) });
  const pending = chat.submit('Pending question');
  chat.restore(turns('Restored question'));
  complete(CHAT_FIXTURES.ok);
  assert.equal(await pending, false);
  assert.equal(chat.snapshot().turns[0].question, 'Restored question');
  assert.equal(chat.snapshot().pending, false);
});

test('multiple store instances merge records and observe deletions before saving', () => {
  const env = setup();
  const other = createHistory(env.options);
  const first = env.history.save(null, turns('First question'));
  other.save(null, turns('Second question'));
  assert.equal(env.history.snapshot().records.length, 2);
  other.remove(first);
  assert.equal(env.history.save(first, turns('Deleted question')), null);
});
