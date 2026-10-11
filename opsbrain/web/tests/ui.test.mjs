import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { AGENTS, ROUTES, agentCard, badge, emptyState, errorState, escapeHtml, loadingState, navigation, renderPage, routeFromHash, validateDraft } from '../public/ui.js';

test('hash routing supports home and every workspace route with safe fallback', () => {
  for (const id of ['home', ...ROUTES.map(route => route.id)]) assert.equal(routeFromHash(`#/${id}`), id);
  for (const value of ['', '#main', '#/<script>', '#/unknown']) assert.equal(routeFromHash(value), 'dashboard');
});
test('navigation exposes exactly one current page and labels future views', () => {
  const html = navigation('dashboard');
  assert.equal((html.match(/aria-current="page"/g) || []).length, 1);
  assert.match(html, /href="#\/dashboard" aria-current="page"/);
  assert.equal((html.match(/class="nav-next"/g) || []).length, 3);
});
test('status badges use visible text and reject unknown state', () => {
  for (const [state, text] of Object.entries({ live: 'Live', demo: 'Demo', disconnected: 'Disconnected', pending: 'Coming next' })) assert.ok(badge(state).includes(text));
  assert.throws(() => badge('healthy'), /Unknown/);
  assert.ok(badge('demo', '<script>').includes('&lt;script&gt;'));
});
test('all four agents remain disconnected and never claim live readiness', () => {
  assert.deepEqual(AGENTS.map(agent => agent.name), ['RAG', 'Monitoring', 'Infra', 'Code']);
  for (const agent of AGENTS) { const html = agentCard(agent); assert.match(html, /Disconnected/); assert.match(html, /Not configured/); assert.ok(!html.includes('badge-live')); }
});
test('dynamic component text is escaped including HTML attributes', () => {
  const unsafe = '<img src=x onerror="alert(1)">';
  assert.equal(escapeHtml(`&<>"'`), '&amp;&lt;&gt;&quot;&#39;');
  for (const html of [emptyState(unsafe, unsafe), errorState(unsafe), agentCard({ name: unsafe, subtitle: unsafe, color: unsafe, icon: 'unknown' })]) { assert.ok(!html.includes('<img')); assert.ok(html.includes('&lt;img')); }
});
test('loading and error examples have accessible status semantics', () => {
  assert.match(loadingState(), /role="status"/);
  assert.match(loadingState(), /aria-label=/);
  assert.match(errorState('Example'), /role="status"/);
});
test('rendered pages have one heading and future features disclose their ticket', () => {
  for (const id of ['home', ...ROUTES.map(route => route.id)]) {
    const page = renderPage(id);
    assert.equal((page.html.match(/<h1>/g) || []).length, 1);
    const ticket = ROUTES.find(route => route.id === id)?.ticket;
    if (ticket) assert.ok(page.html.includes(ticket));
  }
});
test('overview explicitly discloses that no backend requests are made', () => {
  const { html } = renderPage('dashboard');
  assert.match(html, /No backend requests are made/);
  assert.equal((html.match(/class="panel agent-card"/g) || []).length, 4);
});
test('draft validation trims input and does not echo untrusted text', () => {
  assert.match(validateDraft('    '), /at least five/);
  assert.match(validateDraft(' hi '), /at least five/);
  assert.match(validateDraft('<script>alert(1)</script>'), /Nothing was sent or saved/);
  assert.ok(!validateDraft('<script>alert(1)</script>').includes('<script>'));
  assert.match(validateDraft('x'.repeat(2001)), /2000/);
});
test('HTML and CSS include accessible responsive foundation hooks', async () => {
  const html = await readFile(new URL('../public/index.html', import.meta.url), 'utf8');
  const css = await readFile(new URL('../public/styles.css', import.meta.url), 'utf8');
  assert.match(html, /lang="en"/); assert.match(html, /name="viewport"/);
  assert.match(html, /class="skip-link"/); assert.match(html, /aria-controls="workspace-navigation"/);
  assert.match(html, /<main id="main" tabindex="-1">/); assert.match(html, /<noscript>/);
  assert.match(css, /:focus-visible/); assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /max-width: 700px/); assert.match(css, /max-width: 430px/);
});
test('foundation client has no network, credential or persistent storage calls', async () => {
  for (const name of ['app.js', 'ui.js']) {
    const source = await readFile(new URL(`../public/${name}`, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /\b(fetch|XMLHttpRequest|WebSocket|localStorage|sessionStorage)\b/);
    assert.doesNotMatch(source, /LLM_API_KEY|GOOGLE_API_KEY|GITHUB_TOKEN|POSTGRES_PASSWORD/);
  }
});

test('core text and action tokens meet a 4.5:1 contrast baseline', async () => {
  const css = await readFile(new URL('../public/styles.css', import.meta.url), 'utf8');
  const tokens = Object.fromEntries([...css.matchAll(/--([a-z-]+): (#[a-f0-9]{6})/g)].map(match => [match[1], match[2]]));
  function luminance(hex) {
    const rgb = [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16) / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
    return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
  }
  for (const [foreground, background] of [['text', 'bg'], ['text', 'panel'], ['muted', 'panel'], ['quiet', 'panel'], ['accent-ink', 'accent']]) {
    const values = [luminance(tokens[foreground]), luminance(tokens[background])].sort((a, b) => b - a);
    assert.ok((values[0] + .05) / (values[1] + .05) >= 4.5, `${foreground} on ${background}`);
  }
});
