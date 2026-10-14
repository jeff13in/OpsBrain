import test from 'node:test';
import assert from 'node:assert/strict';
import { formattedAnswer, chatResponse } from '../public/ui.js';

test('answer formatting preserves citations outside inert code and escapes active content', () => {
  const text = '**Inspect** [1]\n- Read `pod [1]`\n```sh\n<img onerror=bad> [1]\n```\n[x](javascript:alert(1))';
  const html = formattedAnswer(text, ['runbook'], 'source');
  assert.match(html, /<strong>Inspect<\/strong>/);
  assert.match(html, /<ul><li>Read <code>pod \[1\]<\/code><\/li><\/ul>/);
  assert.match(html, /<pre tabindex="0"><code>&lt;img/);
  assert.equal((html.match(/data-source-target/g) || []).length, 1);
  assert.doesNotMatch(html, /<img|<a |href=|onerror="/);
});

test('unterminated fences, unicode and oversized markup have safe output', () => {
  assert.match(formattedAnswer('```\nλ <script>', [], 's'), /<code>λ &lt;script&gt;<\/code>/);
  assert.doesNotMatch(formattedAnswer('**x**'.repeat(5000), [], 's'), /<strong>/);
  assert.doesNotMatch(formattedAnswer('<svg onload=bad>', [], 's'), /<svg/);
});

test('formatted live partial answer retains status, routing and sources', () => {
  const html = chatResponse({status:'partial', answer:'**Useful** [1]', sources:['runbook'],
    routing:{method:'keyword',agents:['rag','code'],reason:'Selected'}, results:[
      {agent:'rag',status:'ok',answer:'Useful [1]',sources:['runbook'],latency_ms:2},
      {agent:'code',status:'error',sources:[],error:{message:'Unavailable'}}]}, 0, 'live');
  assert.match(html, /<strong>Useful<\/strong>/);
  assert.match(html, /Live · Partial availability/);
  assert.match(html, /Latency: 2 ms/);
  assert.match(html, /Routing: keyword/);
  assert.match(html, /chat-source-0-1/);
});
