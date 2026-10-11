import test from 'node:test';
import assert from 'node:assert/strict';
import { DEMO_FIXTURE, DEMO_STATES, demoState, demoStateFromHash } from '../public/demo.js';
import { AGENTS, demoAgentCard, renderPage } from '../public/ui.js';

test('preview state parsing fails closed to disconnected', () => {
  for (const state of DEMO_STATES) {
    assert.equal(demoStateFromHash(`#/dashboard?state=${state.id}`), state.id);
  }
  for (const value of ['', '#/dashboard', '#/dashboard?state=live', '#/dashboard?state=%3Cscript%3E']) {
    assert.equal(demoStateFromHash(value), 'disconnected');
  }
  assert.equal(demoState({}), 'disconnected');
  assert.equal(demoState(null), 'disconnected');
});

test('synthetic fixtures cannot be changed between previews', () => {
  assert.throws(() => { DEMO_FIXTURE.signals[0].value = '0%'; }, TypeError);
  assert.throws(() => { DEMO_FIXTURE.agents.Code.outcome = 'Healthy'; }, TypeError);
  assert.throws(() => { DEMO_STATES.push({ id: 'live' }); }, TypeError);
});

test('every dashboard state discloses disconnected backend and selects its control', () => {
  for (const { id } of DEMO_STATES) {
    const { html } = renderPage('dashboard', { dashboardState: id });
    assert.match(html, /No backend requests are made/);
    assert.match(html, /Backend disconnected/);
    assert.ok(html.includes(`value="${id}" selected`));
    assert.equal((html.match(/ selected/g) || []).length, 1);
    assert.equal((html.match(/class="panel agent-card"/g) || []).length, 4);
    assert.doesNotMatch(html, /badge-live/);
  }
});

test('populated preview shows deterministic labelled metrics and activity', () => {
  const { html } = renderPage('dashboard', { dashboardState: 'populated' });
  for (const signal of DEMO_FIXTURE.signals) assert.ok(html.includes(signal.value));
  for (const item of DEMO_FIXTURE.activity) assert.ok(html.includes(item.title));
  assert.match(html, /Synthetic context · not connection status/);
  assert.match(html, /Demo only/);
});

test('partial availability preserves successful context and excludes failed Code activity', () => {
  const { html } = renderPage('dashboard', { dashboardState: 'partial' });
  assert.match(html, /Demo partial availability/);
  assert.match(html, /Sample result unavailable/);
  assert.ok(html.includes(DEMO_FIXTURE.signals[0].value));
  assert.ok(html.includes(DEMO_FIXTURE.activity[0].title));
  assert.ok(!html.includes(DEMO_FIXTURE.activity[2].title));
  const code = demoAgentCard(AGENTS.find(agent => agent.name === 'Code'), 'partial');
  assert.doesNotMatch(code, /Sample context ready/);
});

test('unavailable and empty states never reuse successful demo data', () => {
  for (const state of ['loading', 'empty', 'error', 'disconnected', 'live']) {
    const { html } = renderPage('dashboard', { dashboardState: state });
    for (const signal of DEMO_FIXTURE.signals) assert.ok(!html.includes(`<dd>${signal.value}<p>`));
    for (const item of DEMO_FIXTURE.activity) assert.ok(!html.includes(item.title));
    assert.doesNotMatch(html, /Sample context ready/);
  }
  assert.match(renderPage('dashboard', { dashboardState: 'loading' }).html, /no request is in progress/);
  assert.match(renderPage('dashboard', { dashboardState: 'error' }).html, /Reset demo preview/);
});

test('demo cards escape dynamic agent text', () => {
  const html = demoAgentCard({ name: '<script>', subtitle: '<img>', color: '" onclick="bad', icon: 'unknown' }, 'populated');
  assert.doesNotMatch(html, /<script>|<img>| onclick="bad/);
  assert.match(html, /&lt;script&gt;/);
});
