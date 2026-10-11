import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { AGENTS, LANDING_SECTIONS, ROUTES, landingSectionFromHash, navigation, renderPage, routeFromHash } from '../public/ui.js';

test('landing is the default entry point and Home has active navigation', () => {
  assert.equal(routeFromHash(''), 'home');
  assert.equal(routeFromHash('#/home'), 'home');
  assert.match(navigation('home'), /href="#\/home" aria-current="page"/);
  assert.equal((navigation('home').match(/aria-current="page"/g) || []).length, 1);
});

test('landing explains OpsBrain and all four specialists', () => {
  const { html } = renderPage('home');
  assert.match(html, /Connect the dots/);
  assert.match(html, /runbooks, monitoring, infrastructure and code/);
  assert.equal((html.match(/class="panel specialist-card"/g) || []).length, 4);
  for (const agent of AGENTS) assert.ok(html.includes(agent.name));
  assert.match(html, /retrieved context/);
  assert.match(html, /AWS\/cluster acceptance is deferred/);
  assert.match(html, /selected GitHub repository/);
  assert.match(html, /does not create or apply a plan/);
});

test('illustration is explicitly not an executed query or live status', () => {
  const { html } = renderPage('home');
  assert.match(html, /Illustration only/);
  assert.match(html, /Example question · not executed/);
  assert.match(html, /No backend connected/);
  assert.ok(!html.includes('badge-live'));
  assert.ok(!html.includes('All systems operational'));
});

test('landing states audience, missing access protection and current limits', () => {
  const { html } = renderPage('home');
  assert.match(html, /BUILT FOR TWO/);
  assert.match(html, /Not deployed or access-protected yet/);
  assert.match(html, /Not a public production service/);
  assert.match(html, /two approved email identities/);
  assert.match(html, /independently protect any connected API/);
  assert.match(html, /Chat, charts and labelled demo data are next/);
  assert.ok(!/<form|<input|<button/.test(html), 'No signup, payment or fake application action');
});

test('all landing links target existing routes and every section exists', () => {
  const { html } = renderPage('home');
  const known = new Set(ROUTES.map(route => route.id));
  const links = [...html.matchAll(/href="([^"]+)"/g)].map(match => match[1]);
  assert.equal(links.filter(link => link === '#/dashboard').length, 2);
  for (const link of links) {
    assert.ok(link.startsWith('#/'));
    assert.ok(known.has(link.replace(/^#\//, '').split('?')[0]));
    const section = landingSectionFromHash(link);
    if (section) assert.ok(html.includes(`id="${section}" tabindex="-1"`));
  }
  for (const section of LANDING_SECTIONS) assert.ok(links.includes(`#/home?section=${section}`));
});

test('section navigation only accepts known landing sections', () => {
  for (const section of LANDING_SECTIONS) assert.equal(landingSectionFromHash(`#/home?section=${section}`), section);
  for (const hash of ['#/dashboard?section=workflow', '#/home?section=unknown', '#/home?section=%3Cscript%3E', '#/home', '']) assert.equal(landingSectionFromHash(hash), null);
});

test('landing headings and example use semantic HTML and labelled sections', () => {
  const { html } = renderPage('home');
  assert.equal((html.match(/<h1(?:\s[^>]*)?>/g) || []).length, 1);
  assert.match(html, /<blockquote>/);
  assert.match(html, /<ol class="workflow-steps">/);
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(new Set(ids).size, ids.length);
  for (const [, id] of html.matchAll(/aria-labelledby="([^"]+)"/g)) assert.ok(ids.includes(id));
});

test('static entry metadata and responsive rules support the landing', async () => {
  const html = await readFile(new URL('../public/index.html', import.meta.url), 'utf8');
  const css = await readFile(new URL('../public/styles.css', import.meta.url), 'utf8');
  assert.match(html, /Local two-engineer preview; no backend connected/);
  assert.match(css, /\.landing-hero \{ grid-template-columns: 1fr/);
  assert.match(css, /\.specialist-grid, \.scope-grid, \.workflow-steps \{ grid-template-columns: 1fr/);
  assert.doesNotMatch(css, /(?:^|\} )nav \{ display: none/);
});
