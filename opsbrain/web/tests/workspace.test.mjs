import test from 'node:test';
import assert from 'node:assert/strict';
import { createWorkspace, validateWorkspaceSummary, WORKSPACE_SECTIONS, workspaceDemoRoute, workspaceSectionFromHash } from '../public/workspace.js';
import { clientNavigation, renderPage } from '../public/ui.js';
const id = '00000000-0000-4000-8000-000000000002';
const projectId = '00000000-0000-4000-8000-000000000003';
const summary = { workspace: { id, name: 'My workspace' }, profile: { display_name: 'Client A' },
  recent_projects: [{ id: projectId, title: 'Incident review', updated_at: '2026-10-12T12:00:00+00:00', version: 1 }],
  capabilities: { project_writes: false, preferences: false, activity: false, live_tools: false } };
const reply = (body, status = 200) => ({ status, text: async () => JSON.stringify(body) });
const options = { protectedState: { status: 'authorized', workspaceId: id, message: 'Your account is verified.' },
  workspaceState: { status: 'ready', workspaceId: id, data: summary } };

test('six client sections and demo subroutes resolve with safe fallback', () => {
  assert.equal(WORKSPACE_SECTIONS.length, 6);
  for (const { id } of WORKSPACE_SECTIONS) assert.equal(workspaceSectionFromHash(`#/workspace/${id}`), id);
  assert.equal(workspaceDemoRoute('#/workspace/demo-chat'), 'chat');
  assert.equal(workspaceDemoRoute('#/workspace/demo-monitoring'), 'monitoring');
  assert.equal(workspaceSectionFromHash('#/workspace/unknown'), 'dashboard');
  assert.equal(workspaceSectionFromHash('#/workspace/%3Cscript%3E'), 'dashboard');
  assert.equal(workspaceDemoRoute('#/workspace/tools'), null);
});

test('navigation has one current page and real internal targets', () => {
  for (const section of WORKSPACE_SECTIONS) {
    const html = clientNavigation(section.id);
    assert.equal((html.match(/aria-current="page"/g) || []).length, 1);
    assert.equal((html.match(/href="#\/workspace\//g) || []).length, 6);
    assert.doesNotMatch(html, /connect-live|components/);
  }
  assert.match(clientNavigation('demo-chat'), /href="#\/workspace\/tools" aria-current="page"/);
});

test('client screens personalize only after matching authorized workspace data', () => {
  for (const { id } of WORKSPACE_SECTIONS) {
    const html = renderPage('workspace', { ...options, workspaceSection: id }).html;
    assert.equal((html.match(/<h1\b/g) || []).length, 1);
    assert.match(html, /My workspace/);
    assert.match(html, /id="account-logout"/);
  }
  assert.match(renderPage('workspace', options).html, /Welcome back, Client A/);
  for (const protectedState of [{ status: 'anonymous', message: 'Log in' }, { status: 'authorized', workspaceId: projectId, message: 'Verified' }]) {
    const html = renderPage('workspace', { ...options, protectedState }).html;
    assert.doesNotMatch(html, /Client A|My workspace|Incident review/);
  }
});

test('project list, unavailable persistence and settings give truthful states', () => {
  const html = renderPage('workspace', { ...options, workspaceSection: 'projects' }).html;
  assert.match(html, /Incident review/); assert.match(html, /2026-10-12 12:00 UTC/);
  assert.match(html, /Create project — unavailable/); assert.match(html, /type="button" disabled/);
  const empty = structuredClone(options); empty.workspaceState.data.recent_projects = [];
  assert.match(renderPage('workspace', empty).html, /No projects yet/);
  assert.match(renderPage('workspace', { ...options, workspaceSection: 'settings' }).html, /Profile editing is unavailable/);
  assert.match(renderPage('workspace', { ...options, workspaceSection: 'activity' }).html, /complete account activity feed is not available/);
});

test('embedded demo views preserve a single heading and expose no live connection controls', () => {
  for (const section of ['tools', 'demo-chat', 'demo-monitoring', 'demo-history']) {
    const html = renderPage('workspace', { ...options, workspaceSection: section }).html;
    assert.equal((html.match(/<h1\b/g) || []).length, 1);
    assert.doesNotMatch(html, /id="connect-live"|Live API connected/);
    assert.match(html, /Demo|demo|synthetic/);
  }
});

test('workspace/profile/project text is escaped as plain text', () => {
  const unsafe = structuredClone(options);
  unsafe.workspaceState.data.workspace.name = '<script>workspace</script>';
  unsafe.workspaceState.data.profile.display_name = '<img src=x onerror=evil()>';
  unsafe.workspaceState.data.recent_projects[0].title = '<script>project</script>';
  const html = renderPage('workspace', unsafe).html;
  assert.doesNotMatch(html, /<script>|<img src=x/); assert.match(html, /&lt;script&gt;/);
});

test('summary validates ownership, bounds, dates, duplicate IDs and capability gate', () => {
  assert.ok(validateWorkspaceSummary(summary, id));
  for (const mutate of [
    body => { body.workspace.id = projectId; }, body => { body.profile.display_name = 'x'.repeat(121); },
    body => { body.recent_projects[0].updated_at = 'invalid'; }, body => { body.recent_projects.push(body.recent_projects[0]); },
    body => { body.capabilities.live_tools = true; }, body => { body.recent_projects[0].version = Infinity; },
  ]) {
    const body = structuredClone(summary); mutate(body); assert.equal(validateWorkspaceSummary(body, id), null);
  }
});

test('controller uses same-origin credentials and discards extra response metadata', async () => {
  let request;
  const client = createWorkspace({ fetcher: async (url, config) => { request = { url, config }; return reply({ ...summary, provider_token: 'never retain' }); } });
  await client.load(id); assert.equal(client.snapshot().status, 'ready');
  assert.equal(request.url, `/api/workspaces/${id}/summary`); assert.equal(request.config.credentials, 'same-origin');
  assert.equal(request.config.redirect, 'error'); assert.ok(!JSON.stringify(client.snapshot()).includes('never retain'));
  const copy = client.snapshot(); copy.data.workspace.name = 'mutated'; assert.equal(client.snapshot().data.workspace.name, 'My workspace');
});

test('failures and expired identity clear private data rather than reuse it', async () => {
  let response = reply(summary); const redirects = [];
  const client = createWorkspace({ fetcher: async () => response, onUnauthorized: path => redirects.push(path) });
  await client.load(id); response = reply({}, 503); await client.load(id);
  assert.equal(client.snapshot().status, 'error'); assert.equal(client.snapshot().data, null);
  response = reply({}, 401); await client.load(id); assert.equal(client.snapshot().data, null);
  assert.deepEqual(redirects, ['#/login']);
});

test('navigation and logout invalidation reject late private summaries', async () => {
  let finish;
  const client = createWorkspace({ fetcher: () => new Promise(resolve => { finish = resolve; }) });
  const pending = client.load(id); client.leave(); finish(reply(summary)); await pending;
  assert.equal(client.snapshot().data, null); assert.equal(client.snapshot().workspaceId, null);
});
