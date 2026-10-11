import test from 'node:test';
import assert from 'node:assert/strict';
import { HISTORY_KEY } from '../public/history.js';
import { CHAT_FIXTURES } from '../public/chat.js';

class StubElement {
  constructor({ id = '', classes = [], dataset = {} } = {}) {
    this.id = id;
    this.classes = new Set(classes);
    this.dataset = dataset;
    this.listeners = new Map();
    this.attributes = new Map();
    this.textContent = '';
    this.value = '';
    this.selectedOptions = [{ textContent: 'Populated' }];
  }
  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  get classList() {
    const classes = this.classes;
    return {
      add: (...names) => names.forEach(name => classes.add(name)),
      remove: (...names) => names.forEach(name => classes.delete(name)),
      toggle: (name, force) => {
        const willAdd = force === undefined ? !classes.has(name) : Boolean(force);
        if (willAdd) classes.add(name); else classes.delete(name);
        return willAdd;
      },
    };
  }
  focus() { this.focused = (this.focused || 0) + 1; }
  scrollIntoView() {}
  setSelectionRange() {}
  requestSubmit() {
    for (const handler of this.listeners.get('submit') || []) handler({ currentTarget: this, target: this, preventDefault() {} });
  }
}

function fire(element, type, extra = {}) {
  for (const handler of element.listeners.get(type) || []) handler({ currentTarget: element, target: element, preventDefault() {}, ...extra });
}

const registry = new Map();
const dataRegistry = new Map();
const namedElements = new Map();
const staticKeys = new Set();

function defineStatic(key, element) {
  registry.set(key, element);
  staticKeys.add(key);
  return element;
}

function registerFromHtml(html) {
  for (const key of [...registry.keys()]) if (!staticKeys.has(key)) registry.delete(key);
  dataRegistry.clear();
  namedElements.clear();
  for (const [, id] of html.matchAll(/\sid="([^"]+)"/g)) {
    if (!registry.has('#' + id)) registry.set('#' + id, new StubElement({ id }));
  }
  for (const [, classes] of html.matchAll(/\sclass="([^"]+)"/g)) {
    for (const name of classes.split(/\s+/)) {
      if (name && !registry.has('.' + name)) registry.set('.' + name, new StubElement({ classes: [name] }));
    }
  }
  for (const [, name, value] of html.matchAll(/\sdata-([a-z-]+)(?:="([^"]*)")?/g)) {
    if (!dataRegistry.has(name)) dataRegistry.set(name, []);
    dataRegistry.get(name).push(new StubElement({ dataset: { [name]: value ?? '' } }));
  }
  for (const match of html.matchAll(/<(textarea|select|input)[^>]*>/g)) {
    const nameMatch = /\sname="([^"]+)"/.exec(match[0]);
    const idMatch = /\sid="([^"]+)"/.exec(match[0]);
    const element = idMatch && registry.get('#' + idMatch[1]);
    if (nameMatch && element) namedElements.set(nameMatch[1], element);
  }
}

let mainHtml = '';
const main = defineStatic('#main', new StubElement({ id: 'main' }));
Object.defineProperty(main, 'innerHTML', {
  set(value) { mainHtml = String(value); registerFromHtml(mainHtml); },
  get() { return mainHtml; },
});
const nav = defineStatic('#workspace-navigation', new StubElement({ id: 'workspace-navigation' }));
Object.defineProperty(nav, 'innerHTML', { set(value) {}, get() { return ''; } });
defineStatic('#breadcrumb', new StubElement({ id: 'breadcrumb' }));
defineStatic('#announcement', new StubElement({ id: 'announcement' }));
defineStatic('.menu-toggle', new StubElement({ classes: ['menu-toggle'] }));
defineStatic('.skip-link', new StubElement({ classes: ['skip-link'] }));

const windowListeners = new Map();
const windowStub = {
  location: { hash: '' },
  localStorage: {
    store: new Map(),
    getItem(key) { return this.store.has(key) ? this.store.get(key) : null; },
    setItem(key, value) { this.store.set(key, String(value)); },
  },
  addEventListener(type, handler) {
    if (!windowListeners.has(type)) windowListeners.set(type, []);
    windowListeners.get(type).push(handler);
  },
  dispatch(type) { for (const handler of windowListeners.get(type) || []) handler({}); },
};

const documentStub = {
  hidden: false,
  activeElement: null,
  title: '',
  querySelector(selector) {
    if (selector.startsWith('#') || selector.startsWith('.')) return registry.get(selector) || null;
    const match = /^\[data-([a-z-]+)\]$/.exec(selector);
    return match ? (dataRegistry.get(match[1])?.[0] || null) : null;
  },
  querySelectorAll(selector) {
    const match = /^\[data-([a-z-]+)\]$/.exec(selector);
    return match ? [...(dataRegistry.get(match[1]) || [])] : [];
  },
  getElementById(id) { return registry.get('#' + id) || null; },
  addEventListener() {},
};

const fetchCalls = [];
const responses = {
  '/api/orchestrator/health': { status: 'ok', agent: 'orchestrator' },
  '/api/monitoring/alerts/summary': { total: 2, active: 1, suppressed: 0 },
  '/api/monitoring/pods/health': { total_pods: 3, status_breakdown: { Running: 2, Pending: 1 }, pods: [] },
};

globalThis.document = documentStub;
globalThis.window = windowStub;
globalThis.FormData = class {
  constructor(form) { this.form = form; }
  get(name) { return namedElements.get(name)?.value ?? null; };
};
globalThis.fetch = async (url) => {
  const path = String(url).replace(/^https?:\/\/[^/]+/, '');
  fetchCalls.push(path);
  const body = responses[path];
  return body
    ? { status: 200, text: async () => JSON.stringify(body) }
    : { status: 404, text: async () => '{"error":"not found"}' };
};
globalThis.setInterval = () => 0;
globalThis.clearInterval = () => {};

const settle = (ms = 20) => new Promise(resolve => setTimeout(resolve, ms));

// The initial render() runs at import time with moveFocus=false, which is the
// exact path where dashboard controls used to be left unwired.
windowStub.location.hash = '#/dashboard';
await import('../public/app.js');

test('dashboard connection controls are wired on initial load', () => {
  for (const id of ['connect-live', 'use-demo', 'disconnect-api']) {
    const element = documentStub.getElementById(id);
    assert.ok(element, `#${id} is rendered on the dashboard`);
    assert.ok((element.listeners.get('click') || []).length > 0, `#${id} has a click handler`);
  }
  const stateSelect = documentStub.getElementById('demo-state');
  assert.ok(stateSelect, '#demo-state is rendered on the dashboard');
  assert.ok((stateSelect.listeners.get('change') || []).length > 0, '#demo-state has a change handler');
});

test('typing in the chat composer updates the character counter', () => {
  windowStub.location.hash = '#/chat';
  windowStub.dispatch('hashchange');
  const question = documentStub.getElementById('chat-question');
  assert.ok(question, '#chat-question is rendered');
  question.value = 'Why is the website slow?';
  fire(question, 'input');
  assert.equal(documentStub.getElementById('chat-count').textContent, '24 / 2000');
});

test('cmd-enter submits the chat form and renders the demo answer', async () => {
  const question = documentStub.getElementById('chat-question');
  question.value = 'Why is the website slow?';
  documentStub.getElementById('chat-scenario').value = 'ok';
  fire(question, 'keydown', { key: 'Enter', metaKey: true });
  await settle(600);
  assert.match(main.innerHTML, /chat-answer/);
  assert.match(main.innerHTML, /Example answer/);
});

test('the history filter narrows the rendered list', () => {
  const now = Date.now();
  windowStub.localStorage.store.set(HISTORY_KEY, JSON.stringify({ version: 1, records: [
    { id: 'conv-1', mode: 'demo', createdAt: now, updatedAt: now, turns: [{ question: 'Why is the website slow?', response: CHAT_FIXTURES.partial }] },
    { id: 'conv-2', mode: 'demo', createdAt: now, updatedAt: now, turns: [{ question: 'How are the pods?', response: CHAT_FIXTURES.partial }] },
  ] }));
  windowStub.location.hash = '#/history';
  windowStub.dispatch('hashchange');
  assert.equal(dataRegistry.get('open-history')?.length, 2);
  const filter = documentStub.getElementById('history-filter');
  filter.value = 'website';
  fire(filter, 'input');
  assert.equal(dataRegistry.get('open-history')?.length, 1);
  assert.match(main.innerHTML, /1 of 2 \/ 20/);
});

test('the monitoring error state resets to populated samples', async () => {
  windowStub.location.hash = '#/monitoring';
  windowStub.dispatch('hashchange');
  documentStub.getElementById('monitoring-range').value = '15m';
  const scenario = documentStub.getElementById('monitoring-scenario');
  scenario.value = 'error';
  fire(scenario, 'change');
  await settle(500);
  assert.ok(documentStub.getElementById('monitoring-reset'), 'reset button appears in the error state');
  fire(documentStub.getElementById('monitoring-reset'), 'click');
  await settle(500);
  assert.match(main.innerHTML, /<polyline/);
});

test('connect live queries the orchestrator health endpoint', async () => {
  windowStub.location.hash = '#/dashboard';
  windowStub.dispatch('hashchange');
  fire(documentStub.getElementById('connect-live'), 'click');
  await settle();
  assert.ok(fetchCalls.includes('/api/orchestrator/health'), 'health endpoint was queried');
});

test('returning to a live dashboard does not throw without a demo state select', () => {
  windowStub.location.hash = '#/dashboard';
  assert.doesNotThrow(() => windowStub.dispatch('hashchange'));
  assert.equal(documentStub.getElementById('breadcrumb').textContent, 'Overview');
});

test('live monitoring refresh is wired and queries both snapshot endpoints', async () => {
  windowStub.location.hash = '#/monitoring';
  windowStub.dispatch('hashchange');
  const refresh = documentStub.getElementById('live-monitoring-refresh');
  assert.ok(refresh, '#live-monitoring-refresh is rendered in live monitoring');
  assert.ok((refresh.listeners.get('click') || []).length > 0, 'refresh has a click handler');
  const before = fetchCalls.length;
  fire(refresh, 'click');
  await settle();
  const calls = fetchCalls.slice(before);
  assert.ok(calls.includes('/api/monitoring/alerts/summary'), 'alerts summary endpoint was queried');
  assert.ok(calls.includes('/api/monitoring/pods/health'), 'pods health endpoint was queried');
});
