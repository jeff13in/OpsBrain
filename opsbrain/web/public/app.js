import { createApi } from './api.js';
import { createHistory, HISTORY_KEY } from './history.js';
import { createMonitoring } from './monitoring.js';
import { createChat, demoReply } from './chat.js';
import { demoStateFromHash } from './demo.js';
import { landingSectionFromHash, navigation, renderPage, routeFromHash, validateDraft } from './ui.js';

const main = document.querySelector('#main');
const nav = document.querySelector('#workspace-navigation');
const toggle = document.querySelector('.menu-toggle');
let apiMode = 'demo';
const api = createApi({ onChange() {
  const mode = api.snapshot().mode;
  const changed = mode !== apiMode;
  apiMode = mode;
  if (changed || routeFromHash(window.location.hash) === 'monitoring') render();
} });
const history = createHistory();
let activeHistoryId = null;
let restoringHistory = false;
let historyFilter = '';
const chat = createChat({ reply: (scenario, question) => chat.snapshot().mode === 'live' ? api.ask(question) : demoReply(scenario), onChange() {
  const state = chat.snapshot();
  if (state.mode !== 'live' && !state.pending && !state.validation && state.turns.length && !restoringHistory) {
    const savedId = history.save(activeHistoryId, state.turns);
    if (!savedId && activeHistoryId) {
      activeHistoryId = null;
      chat.clear();
      document.querySelector('#announcement').textContent = 'The saved conversation expired or was deleted. Start a new conversation.';
      return;
    }
    activeHistoryId = savedId;
  }
  const route = routeFromHash(window.location.hash);
  if (route === 'history') { render(); return; }
  if (route !== 'chat') return;
  render();
  document.querySelector('#announcement').textContent = state.validation || (state.pending ? state.mode === 'live' ? 'Waiting for the live API answer.' : 'Preparing a fixed demo answer.' : state.turns.length ? `${state.mode === 'live' ? 'Live' : 'Demo'} answer ready. Sources and per-agent results follow your question.` : 'Demo conversation cleared.');
  if (state.validation) document.querySelector('#chat-question')?.focus();
  else if (!state.pending && state.turns.length) {
    document.querySelector(`#chat-answer-${state.turns.length - 1}`)?.focus();
  } else if (!state.pending) document.querySelector('#chat-question')?.focus();
} });

const monitoring = createMonitoring({ onChange() {
  if (routeFromHash(window.location.hash) !== 'monitoring' || document.hidden) return;
  const focused = document.activeElement?.id;
  render();
  if (focused?.startsWith('monitoring-')) document.getElementById(focused)?.focus();
  const state = monitoring.snapshot();
  document.querySelector('#announcement').textContent = state.pending ? 'Refreshing synthetic monitoring samples.' : `Demo monitoring: ${state.scenario}. Backend disconnected.`;
} });

function render(moveFocus = false) {
  const route = routeFromHash(window.location.hash);
  if (route !== 'history') historyFilter = '';
  if (activeHistoryId && !history.get(activeHistoryId)) { activeHistoryId = null; chat.clear(); }
  monitoring.setActive(route === 'monitoring' && api.snapshot().mode === 'demo' && !document.hidden);
  let historyState = history.snapshot();
  if (route === 'history') {
    const total = historyState.records.length;
    const records = historyFilter ? historyState.records.filter(record => record.turns[0].question.toLowerCase().includes(historyFilter.toLowerCase())) : historyState.records;
    historyState = { ...historyState, records, total };
  }
  const page = renderPage(route, { dashboardState: demoStateFromHash(window.location.hash), chatState: chat.snapshot(), monitoringState: monitoring.snapshot(), historyState, historyFilter, connectionState: api.snapshot() });
  nav.innerHTML = navigation(route);
  // Renderers contain trusted templates; all dynamic text is escaped in ui.js.
  main.innerHTML = page.html;
  main.classList.toggle('landing-page', route === 'home');
  document.querySelector('#breadcrumb').textContent = page.title;
  document.title = `${page.title} — OpsBrain`;
  toggle.setAttribute('aria-expanded', 'false');
  nav.classList.remove('is-open');
  if (moveFocus) main.focus();
  if (route === 'dashboard') {
    document.querySelector('#connect-live')?.addEventListener('click', () => {
      activeHistoryId = null; monitoring.setActive(false); chat.setMode('live'); void api.connect();
    });
    for (const [id, mode] of [['use-demo', 'demo'], ['disconnect-api', 'disconnected']]) {
      document.getElementById(id)?.addEventListener('click', () => {
        activeHistoryId = null; monitoring.setActive(false); api.disconnect(mode); chat.setMode(mode === 'demo' ? 'demo' : 'live');
      });
    }
    if (moveFocus) {
      const stateSelect = document.querySelector('#demo-state');
      stateSelect?.focus();
      if (stateSelect) document.querySelector('#announcement').textContent = `Dashboard preview: ${stateSelect.selectedOptions[0].textContent}. Backend disconnected.`;
    }
  }
  document.querySelector('#live-monitoring-refresh')?.addEventListener('click', () => { void api.refreshMonitoring(); });
  const section = landingSectionFromHash(window.location.hash);
  if (section) {
    const target = document.getElementById(section);
    target?.scrollIntoView({ block: 'start' });
    target?.focus({ preventScroll: true });
  }
  document.querySelector('#demo-state')?.addEventListener('change', event => {
    window.location.hash = `/dashboard?state=${event.currentTarget.value}`;
  });
  for (const id of ['monitoring-scenario', 'monitoring-range']) {
    document.getElementById(id)?.addEventListener('change', () => {
      void monitoring.select(document.querySelector('#monitoring-scenario').value, document.querySelector('#monitoring-range').value);
    });
  }
  document.querySelector('#monitoring-refresh')?.addEventListener('click', () => { void monitoring.refresh(); });
  document.querySelector('#monitoring-auto')?.addEventListener('change', event => monitoring.setAuto(event.currentTarget.checked));
  document.querySelector('#chat-form')?.addEventListener('submit', event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (activeHistoryId && !history.get(activeHistoryId)) {
      activeHistoryId = null;
      chat.clear();
    }
    void chat.submit(form.get('question'), form.get('scenario'));
  });
  document.querySelector('#chat-question')?.addEventListener('input', event => {
    const counter = document.querySelector('#chat-count');
    if (counter) counter.textContent = `${event.currentTarget.value.length} / 2000`;
  });
  document.querySelector('#chat-question')?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      document.querySelector('#chat-form')?.requestSubmit();
    }
  });
  const filterInput = document.querySelector('#history-filter');
  filterInput?.addEventListener('input', event => {
    historyFilter = event.currentTarget.value.trim();
    render();
    const input = document.querySelector('#history-filter');
    input?.focus();
    input?.setSelectionRange?.(input.value.length, input.value.length);
  });
  document.querySelector('#monitoring-reset')?.addEventListener('click', () => {
    void monitoring.select('populated', document.querySelector('#monitoring-range')?.value || '15m');
  });
  document.querySelector('#clear-chat')?.addEventListener('click', () => { activeHistoryId = null; api.newSession(); chat.clear(); });
  document.querySelectorAll('[data-open-history]').forEach(button => button.addEventListener('click', () => {
    const record = history.get(button.dataset.openHistory);
    if (!record) { render(); document.querySelector('#announcement').textContent = 'This conversation expired or was deleted.'; return; }
    api.disconnect('demo');
    activeHistoryId = record.id;
    restoringHistory = true;
    chat.restore(record.turns);
    restoringHistory = false;
    window.location.hash = '/chat';
  }));
  document.querySelectorAll('[data-delete-history]').forEach(button => button.addEventListener('click', () => {
    history.remove(button.dataset.deleteHistory);
    if (activeHistoryId === button.dataset.deleteHistory) { activeHistoryId = null; chat.clear(); }
    render();
    document.querySelector('#main').focus();
    document.querySelector('#announcement').textContent = 'Conversation removed from available history. Check the storage notice for persistence.';
  }));
  document.querySelector('#clear-history')?.addEventListener('click', () => {
    history.clear(); activeHistoryId = null; chat.clear(); render(); main.focus();
    document.querySelector('#announcement').textContent = 'Available history cleared. Check the storage notice for persistence.';
  });
  document.querySelectorAll('[data-source-target]').forEach(button => {
    button.addEventListener('click', () => {
      const target = document.getElementById(button.dataset.sourceTarget);
      target?.scrollIntoView({ block: 'nearest' });
      target?.focus({ preventScroll: true });
    });
  });
  document.querySelector('#draft-form')?.addEventListener('submit', event => {
    event.preventDefault();
    document.querySelector('#draft-result').textContent = validateDraft(new FormData(event.currentTarget).get('draft'));
  });
  document.querySelector('[data-preview-action]')?.addEventListener('click', event => {
    event.currentTarget.textContent = 'Checked · no backend action';
    document.querySelector('#announcement').textContent = 'Interface interaction checked. No backend action was performed.';
  });
}

toggle.addEventListener('click', () => {
  const open = toggle.getAttribute('aria-expanded') !== 'true';
  toggle.setAttribute('aria-expanded', String(open));
  nav.classList.toggle('is-open', open);
});

document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault();
  main.focus();
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
    toggle.setAttribute('aria-expanded', 'false');
    nav.classList.remove('is-open');
    toggle.focus();
  }
});

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) refreshHistory();
  monitoring.setActive(routeFromHash(window.location.hash) === 'monitoring' && api.snapshot().mode === 'demo' && !document.hidden);
  if (!document.hidden && routeFromHash(window.location.hash) === 'monitoring') render();
});

function refreshHistory() {
  if (document.hidden) return;
  const route = routeFromHash(window.location.hash);
  if (activeHistoryId && !history.get(activeHistoryId)) { activeHistoryId = null; chat.clear(); }
  if (route === 'history') render();
}
window.addEventListener('storage', event => {
  if (event.key === HISTORY_KEY || event.key === null) refreshHistory();
});
setInterval(refreshHistory, 60000);

window.addEventListener('hashchange', () => render(true));
render();
