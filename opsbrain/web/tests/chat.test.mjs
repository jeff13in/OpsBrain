import test from 'node:test';
import assert from 'node:assert/strict';
import { CHAT_FIXTURES, createChat, validateQuestion } from '../public/chat.js';
import { chatResponse, citedText, renderPage } from '../public/ui.js';

test('question validation trims input and enforces length without echoing it', () => {
  for (const value of [null, '', '    ', ' hi ', 'x'.repeat(2001)]) assert.ok(validateQuestion(value));
  assert.equal(validateQuestion('  Why is the website slow?  '), '');
  assert.equal(validateQuestion('x'.repeat(2000)), '');
});

test('chat prevents duplicate submits and retains ordered turns across responses', async () => {
  let complete;
  let calls = 0;
  const chat = createChat({ reply: () => { calls++; return new Promise(resolve => { complete = resolve; }); } });
  const pending = chat.submit('Why is the website slow?', 'partial');
  assert.equal(chat.snapshot().pending, true);
  assert.equal(chat.snapshot().turns[0].response, null);
  assert.equal(await chat.submit('Another question'), false);
  assert.equal(calls, 1);
  complete(CHAT_FIXTURES.partial);
  assert.equal(await pending, true);
  assert.equal(chat.snapshot().pending, false);
  assert.equal(chat.snapshot().turns[0].response.status, 'partial');
  const second = chat.submit('What should I inspect next?', 'ok');
  complete(CHAT_FIXTURES.ok);
  await second;
  assert.equal(chat.snapshot().turns.length, 2);
  assert.equal(chat.snapshot().turns[0].response.status, 'partial');
});

test('clearing pending chat discards stale completion without erasing a new turn', async () => {
  const resolvers = [];
  const chat = createChat({ reply: () => new Promise(resolve => resolvers.push(resolve)) });
  const first = chat.submit('First question');
  chat.clear();
  const second = chat.submit('Second question');
  resolvers[0](CHAT_FIXTURES.ok);
  assert.equal(await first, false);
  assert.equal(chat.snapshot().pending, true);
  assert.equal(chat.snapshot().turns.length, 1);
  resolvers[1](CHAT_FIXTURES.partial);
  await second;
  assert.equal(chat.snapshot().turns[0].question, 'Second question');
  chat.clear();
  assert.equal(chat.snapshot().turns.length, 0);
});

test('invalid submissions make no response call and page memory is bounded', async () => {
  let calls = 0;
  const chat = createChat({ reply: async () => { calls++; return CHAT_FIXTURES.ok; } });
  assert.equal(await chat.submit('hi'), false);
  assert.equal(await chat.submit('Valid question', 'unknown'), false);
  assert.equal(calls, 0);
  for (let i = 0; i < 20; i++) await chat.submit(`Question ${i}`);
  assert.equal(await chat.submit('Question twenty one'), false);
  assert.equal(calls, 20);
  assert.match(chat.snapshot().validation, /Clear/);
  assert.throws(() => { chat.snapshot().turns.push({}); }, TypeError);
});

test('unexpected demo preparation failure becomes an error without successful sources', async () => {
  const chat = createChat({ reply: async () => { throw new Error('private error text'); } });
  await chat.submit('Valid question');
  const state = chat.snapshot();
  assert.equal(state.pending, false);
  assert.equal(state.turns[0].response.status, 'error');
  assert.deepEqual(state.turns[0].response.sources, []);
  assert.doesNotMatch(state.turns[0].response.answer, /private error text/);
});

test('partial and failed examples show agent failures without fabricating sources', () => {
  const partial = chatResponse(CHAT_FIXTURES.partial, 0);
  assert.match(partial, /Partial availability/);
  assert.match(partial, /Sample unavailable/);
  assert.ok(partial.includes(CHAT_FIXTURES.ok.results[0].answer.split(' [')[0]));
  assert.doesNotMatch(partial, /Example deployment change/);
  const error = chatResponse(CHAT_FIXTURES.error, 1);
  assert.match(error, /No sources available/);
  assert.equal((error.match(/Sample unavailable/g) || []).length, 4);
  assert.doesNotMatch(error, /data-source-target/);
});

test('questions, answers and sources render as escaped plain text', () => {
  const unsafe = '<img src=x onerror="alert(1)"> [click](javascript:alert(1))';
  const response = { status: 'ok', answer: unsafe, sources: [unsafe], results: [{ agent: 'rag', status: 'ok', answer: unsafe, sources: [unsafe] }] };
  const html = renderPage('chat', { chatState: { turns: [{ question: unsafe, response }], pending: false, draft: '</textarea><script>bad</script>', validation: unsafe, scenario: 'ok' } }).html;
  assert.doesNotMatch(html, /<img|<script>|href="javascript:/);
  assert.match(html, /&lt;img/);
  assert.match(html, /&lt;\/textarea&gt;/);
});

test('only existing citations become focus buttons and targets are unique per turn', () => {
  const html = citedText('Inspect [1], not invented [9] or [0].', ['source'], 'turn-0');
  assert.match(html, /data-source-target="turn-0-1"/);
  assert.match(html, /\[9\]/);
  assert.equal((html.match(/<button/g) || []).length, 1);
  for (const index of [0, 1]) {
    const answer = chatResponse(CHAT_FIXTURES.ok, index);
    for (const [, target] of answer.matchAll(/data-source-target="([^"]+)"/g)) {
      assert.ok(answer.includes(`id="${target}" tabindex="-1"`));
    }
  }
});

test('chat empty and loading views disclose demo boundaries with labelled controls', () => {
  const empty = renderPage('chat').html;
  assert.match(empty, /fixed example, independent of your question/);
  assert.match(empty, /No model or backend is called/);
  assert.match(empty, /label for="chat-question"/);
  assert.match(empty, /label for="chat-scenario"/);
  assert.doesNotMatch(empty, /badge-live/);
  const loading = renderPage('chat', { chatState: { turns: [{ question: 'Valid question', response: null }], pending: true, validation: '', draft: '', scenario: 'ok' } }).html;
  assert.match(loading, /aria-busy="true"/);
  assert.match(loading, /Preparing a fixed demo answer/);
  assert.match(loading, /type="submit" disabled/);
});
