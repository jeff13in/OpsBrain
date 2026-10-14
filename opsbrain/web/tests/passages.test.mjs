import test from 'node:test';
import assert from 'node:assert/strict';
import { validatePassage, openSourceTarget } from '../public/sources.js';
import { createPassageClient } from '../public/source-api.js';
import { retrievedPassageDetails } from '../public/ui.js';
const id = 'src_' + 'a'.repeat(64);
const user = '00000000-0000-4000-8000-000000000001';
const workspace = '00000000-0000-4000-8000-000000000002';
const investigation = '00000000-0000-4000-8000-000000000003';
const identity = { authorized: true, liveSourcesEnabled: true, userId: user, workspaceId: workspace };
const value = () => ({ source_id: id, available: true, provenance: 'retrieved', passage: '<script>診断 🧠</script>\n[link](javascript:alert(1))', revision: 'revision 1', observed_at: '2026-10-13T12:00:00Z' });
const response = body => ({ status: 200, text: async () => JSON.stringify(body) });

test('passage response preserves exact plain text, revision and observation; drops hidden metadata', () => {
  assert.deepEqual(validatePassage({ ...value(), secret: 'not exported' }, id), value());
  const unavailable = { source_id: id, available: false, provenance: 'retrieved' };
  assert.equal(validatePassage(unavailable, id).passage, null);
});
test('response rejects hostile IDs, mismatches, oversize, synthetic provenance and impossible timestamps', () => {
  for (const change of [{ source_id: '../secret' }, { provenance: 'demo' }, { passage: 'x'.repeat(8001) },
    { revision: 'x'.repeat(201) }, { observed_at: '2026-02-30T12:00:00Z' }, { available: false }, { passage: '' }]) {
    assert.throws(() => validatePassage({ ...value(), ...change }, id));
  }
});
test('login alone, foreign scope and hostile inputs do not make requests', async () => {
  let requests = 0;
  const client = createPassageClient({ fetcher: async () => { requests++; return response(value()); } });
  assert.equal(await client.load(investigation, id), false);
  client.authorize({ ...identity, liveSourcesEnabled: false });
  assert.equal(await client.load(investigation, id), false);
  client.authorize(identity);
  for (const bad of ['../file', 'https://example.test', '%2e%2e', id + '\n']) assert.equal(await client.load(investigation, bad), false);
  assert.equal(requests, 0);
});
test('authorized adapter calls only scoped same-origin route with no provider token', async () => {
  const client = createPassageClient({ fetcher: async (url, options) => {
    assert.equal(url, `/api/workspaces/${workspace}/investigations/${investigation}/sources/${id}`);
    assert.equal(options.credentials, 'same-origin'); assert.equal(options.cache, 'no-store'); assert.equal(options.redirect, 'error');
    assert.equal(options.headers.Authorization, undefined); return response(value());
  } });
  client.authorize(identity);
  assert.equal(await client.load(investigation, id), true);
  assert.deepEqual(client.snapshot().value, value());
  client.leave(); assert.equal(client.snapshot().value, null);
});
test('late response cannot survive logout/account switching even when transport ignores abort', async () => {
  let done;
  const client = createPassageClient({ fetcher: () => new Promise(resolve => { done = resolve; }) });
  client.authorize(identity);
  const pending = client.load(investigation, id);
  client.authorize({ ...identity, userId: investigation });
  done(response(value()));
  assert.equal(await pending, false); assert.equal(client.snapshot().value, null);
});
test('latest source wins and outages/revocation clear previous private content', async () => {
  let done, requests = 0;
  const client = createPassageClient({ fetcher: () => ++requests === 1 ? new Promise(resolve => { done = resolve; }) : Promise.resolve(response(value())) });
  client.authorize(identity);
  const old = client.load(investigation, id);
  assert.equal(await client.load(investigation, id), true);
  done(response({ ...value(), passage: 'stale' }));
  assert.equal(await old, false); assert.equal(client.snapshot().value.passage, value().passage);
  client.authorize(identity); assert.equal(client.snapshot().value, null);
  const failed = createPassageClient({ fetcher: async () => ({ status: 404, text: async () => 'private error' }) });
  failed.authorize(identity); assert.equal(await failed.load(investigation, id), false);
  assert.equal(failed.snapshot().value, null);
});
test('oversized responses and deadlines stay unavailable without private error text', async () => {
  const client = createPassageClient({ fetcher: async () => ({ status: 200, text: async () => 'x'.repeat(65537) }) });
  client.authorize(identity); assert.equal(await client.load(investigation, id), false);
  const timed = createPassageClient({ timeoutMs: 1, fetcher: async () => {
    await new Promise(resolve => setTimeout(resolve, 5)); return response(value());
  } });
  timed.authorize(identity); assert.equal(await timed.load(investigation, id), false);
  assert.equal(timed.snapshot().status, 'unavailable');
});

test('retrieved passages and metadata render as escaped plain text with native disclosure', () => {
  const html = retrievedPassageDetails({ ...value(), revision: '<img src=x>' }, id);
  assert.match(html, /Read retrieved passage/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&lt;img src=x&gt;/);
  assert.doesNotMatch(html, /<script>|<img /);
  assert.match(html, /診断 🧠/);
  assert.match(retrievedPassageDetails({ ...value(), revision: null, observed_at: null }, id), /Revision unavailable.*Observation time unavailable/);
  assert.match(retrievedPassageDetails({ ...value(), passage: 'x'.repeat(8001) }, id), /Passage unavailable/);
});
test('Escape closes disclosure and restores the invoking citation focus', () => {
  let handler, focused = false, prevented = false;
  const detail = { open: false, dataset: {}, addEventListener(name, callback) { assert.equal(name, 'keydown'); handler = callback; } };
  const target = { querySelector: () => detail, scrollIntoView() {}, focus() {} };
  openSourceTarget(target, { focus() { focused = true; } });
  assert.equal(detail.open, true);
  handler({ key: 'Escape', preventDefault() { prevented = true; } });
  assert.equal(detail.open, false); assert.equal(focused, true); assert.equal(prevented, true);
});
