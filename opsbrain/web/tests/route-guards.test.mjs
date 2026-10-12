import test from 'node:test';
import assert from 'node:assert/strict';
import { createProtectedSession, safePostLoginDestination } from '../public/route-guards.js';
import { renderPage } from '../public/ui.js';
const workspace = '00000000-0000-4000-8000-000000000002';
const valid = { authenticated: true, verified: true, user_id: '00000000-0000-4000-8000-000000000001', workspace_ids: [workspace], csrf_token: 'a'.repeat(32) };
const reply = (body, status = 200) => ({ status, text: async () => JSON.stringify(body) });

test('safe post-login destinations reject external, encoded and unsupported paths', () => {
  assert.equal(safePostLoginDestination('#/home'), '#/home');
  for (const value of ['https://evil.test', '//evil.test', '#/workspace?owner=forged', '#/workspace\n', '%23/workspace', null]) {
    assert.equal(safePostLoginDestination(value), '#/workspace');
  }
});

test('anonymous and unverified users redirect without private state', async () => {
  for (const [response, destination] of [[reply({}, 401), '#/login'], [reply({ authenticated: false }), '#/login'], [reply({ authenticated: true, verified: false }), '#/verification']]) {
    const paths = [];
    const guard = createProtectedSession({ fetcher: async () => response, onRedirect: path => paths.push(path) });
    await guard.load(); assert.deepEqual(paths, [destination]); assert.equal(guard.snapshot().workspaceId, null);
  }
});

test('authorized session resolves server-owned workspace with cookie credentials', async () => {
  let options;
  const guard = createProtectedSession({ fetcher: async (path, config) => { assert.equal(path, '/api/auth/session'); options = config; return reply(valid); } });
  await guard.load();
  assert.equal(options.credentials, 'same-origin'); assert.equal(options.redirect, 'error');
  assert.equal(guard.snapshot().workspaceId, workspace);
  assert.ok(!JSON.stringify(guard.snapshot()).includes(valid.csrf_token));
  assert.match(renderPage('workspace', { protectedState: guard.snapshot() }).html, /id="account-logout"/);
});

test('malformed identity/membership and outages never authorize the workspace', async () => {
  for (const response of [reply(null), reply({}, 503), reply({ ...valid, workspace_ids: [] }), reply({ ...valid, workspace_ids: ['forged'] }), reply({ ...valid, csrf_token: null }), reply({ ...valid, verified: 'true' })]) {
    const guard = createProtectedSession({ fetcher: async () => response });
    await guard.load(); assert.equal(guard.snapshot().status, 'unavailable'); assert.equal(guard.snapshot().workspaceId, null);
  }
});

test('navigation cancellation discards late private state', async () => {
  let finish;
  const guard = createProtectedSession({ fetcher: () => new Promise(resolve => { finish = resolve; }) });
  const pending = guard.load(); guard.leave(); finish(reply(valid)); await pending;
  assert.equal(guard.snapshot().workspaceId, null);
  assert.equal(guard.snapshot().status, 'checking');
});

test('logout clears state immediately and confirms server revocation before redirect', async () => {
  let finish, headers;
  const redirects = [];
  const guard = createProtectedSession({ fetcher: (path, options) => path === '/api/auth/session' ? Promise.resolve(reply(valid))
    : new Promise(resolve => { finish = resolve; headers = options.headers; }), onRedirect: path => redirects.push(path) });
  await guard.load(); const pending = guard.logout();
  assert.equal(guard.snapshot().workspaceId, null);
  assert.equal(headers['X-CSRF-Token'], valid.csrf_token);
  finish(reply({ ok: true })); assert.equal(await pending, true);
  assert.deepEqual(redirects, ['#/login']);
});

test('failed logout clears private display but reports that revocation is unconfirmed', async () => {
  const redirects = [];
  const guard = createProtectedSession({ fetcher: async path => path === '/api/auth/session' ? reply(valid) : reply({}, 503), onRedirect: path => redirects.push(path) });
  await guard.load(); assert.equal(await guard.logout(), false);
  assert.equal(guard.snapshot().workspaceId, null); assert.match(guard.snapshot().message, /could not be confirmed/);
  assert.deepEqual(redirects, []);
});
