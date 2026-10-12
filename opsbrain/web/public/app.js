import { downloadInvestigation } from './investigation.js';
import { openSourceTarget } from './sources.js';
import { createApi } from './api.js';
import { AUTH_ROUTES, createAuth } from './auth.js';
import { createProtectedSession, safePostLoginDestination } from './route-guards.js';
import { createHistory, HISTORY_KEY } from './history.js';
import { createMonitoring } from './monitoring.js';
import { createChat, demoReply } from './chat.js';
import { demoStateFromHash } from './demo.js';
import { clientNavigation, landingSectionFromHash, navigation, renderPage, routeFromHash, validateDraft } from './ui.js';
import { createWorkspace, workspaceDemoRoute, workspaceSectionFromHash } from './workspace.js';
import { accountPayload, createPersistence } from './persistence.js';

const main = document.querySelector('#main');
const nav = document.querySelector('#workspace-navigation');
const toggle = document.querySelector('.menu-toggle');
const isAuthRoute = () => AUTH_ROUTES.some(item => item.id === routeFromHash(window.location.hash));
function contentRoute() {
  const root = routeFromHash(window.location.hash);
  return root === 'workspace' ? workspaceDemoRoute(window.location.hash) || root : root;
}
const persistence = createPersistence({ sendMutation:command=>accountSession.mutate(command), onChange(){
  if(routeFromHash(window.location.hash)==='workspace')render();
},onSaved(){return workspace.load(accountSession.snapshot().workspaceId);} });
const workspace = createWorkspace({ onChange() {
  if (routeFromHash(window.location.hash) === 'workspace') {
    const state=workspace.snapshot();
    if(state.status==='error')persistence.leave();
    render(); document.getElementById('workspace-data-status')?.focus();
    if(state.status==='ready'&&state.data.capabilities.project_writes&&persistence.snapshot().workspaceId!==state.workspaceId)void persistence.load(state.workspaceId);
    if(state.status==='ready'&&window.location.hash==='#/workspace'&&state.data.profile.preferences?.default_section&&state.data.profile.preferences.default_section!=='dashboard')window.location.hash=`#/workspace/${state.data.profile.preferences.default_section}`;
  }
}, onUnauthorized(destination) { accountSession.leave(); window.location.hash = destination; } });
const accountSession = createProtectedSession({ onChange() {
  if (routeFromHash(window.location.hash) !== 'workspace') return;
  const state = accountSession.snapshot();
  if (state.status !== 'authorized') { workspace.leave(); persistence.leave(); }
  render(); document.getElementById('workspace-status')?.focus();
  if (state.status === 'authorized' && workspace.snapshot().workspaceId !== state.workspaceId) void workspace.load(state.workspaceId);
}, onRedirect(destination) { window.location.hash = destination; } });
const auth = createAuth({ async onLogin() {
  const next = new URLSearchParams(window.location.hash.split('?')[1] || '').get('next');
  await accountSession.load();
  if (accountSession.snapshot().status === 'authorized') window.location.hash = safePostLoginDestination(next);
}, onChange() {
  if (!isAuthRoute()) return;
  render();
  const state = auth.snapshot();
  const field = Object.keys(state.errors)[0];
  document.getElementById(field ? `auth-${field}` : 'auth-status')?.focus();
} });
let apiMode = 'demo';
const api = createApi({ onChange() {
  const mode = api.snapshot().mode;
  const changed = mode !== apiMode;
  apiMode = mode;
  if (changed || contentRoute() === 'monitoring') render();
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
  const route = contentRoute();
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
  if (contentRoute() !== 'monitoring' || document.hidden) return;
  const focused = document.activeElement?.id;
  render();
  if (focused?.startsWith('monitoring-')) document.getElementById(focused)?.focus();
  const state = monitoring.snapshot();
  document.querySelector('#announcement').textContent = state.pending ? 'Refreshing synthetic monitoring samples.' : `Demo monitoring: ${state.scenario}. Backend disconnected.`;
} });

function render(moveFocus = false) {
  const root = routeFromHash(window.location.hash);
  const route = contentRoute();
  if (route !== 'history') historyFilter = '';
  if (activeHistoryId && !history.get(activeHistoryId)) { activeHistoryId = null; chat.clear(); }
  monitoring.setActive(route === 'monitoring' && api.snapshot().mode === 'demo' && !document.hidden);
  let historyState = history.snapshot();
  if (route === 'history') {
    const total = historyState.records.length;
    const records = historyFilter ? historyState.records.filter(record => record.turns[0].question.toLowerCase().includes(historyFilter.toLowerCase())) : historyState.records;
    historyState = { ...historyState, records, total };
  }
  const page = renderPage(root, { dashboardState: demoStateFromHash(window.location.hash), chatState: chat.snapshot(), monitoringState: monitoring.snapshot(), historyState, historyFilter, connectionState: api.snapshot(), authState: auth.snapshot(), protectedState: accountSession.snapshot(), workspaceState: workspace.snapshot(), workspaceSection: workspaceSectionFromHash(window.location.hash), persistenceState:persistence.snapshot() });
  nav.innerHTML = root === 'workspace' ? clientNavigation(workspaceSectionFromHash(window.location.hash)) : navigation(route);
  const data = root === 'workspace' && accountSession.snapshot().status === 'authorized' ? workspace.snapshot().data : null;
  document.body?.classList.toggle('account-reduced-motion',Boolean(data?.profile.preferences?.reduced_motion));
  const label = document.getElementById('workspace-label-copy');
  if (label) label.textContent = data?.workspace.name || (root === 'workspace' ? 'Client workspace' : 'Engineer workspace');
  const mode = document.getElementById('workspace-mode');
  if (mode) mode.textContent = root === 'workspace' ? 'Client beta' : 'Private preview';
  const footer = document.getElementById('workspace-footer-state');
  if (footer) footer.textContent = root === 'workspace' ? data ? 'Authorized account data · Demo tools only' : 'Client workspace access pending' : 'No backend connected · Read-only foundation';
  // Renderers contain trusted templates; all dynamic text is escaped in ui.js.
  main.innerHTML = page.html;
  main.classList.toggle('landing-page', route === 'home');
  document.querySelector('#breadcrumb').textContent = page.title;
  document.title = `${page.title} — OpsBrain`;
  toggle.setAttribute('aria-expanded', 'false');
  nav.classList.remove('is-open');
  if (moveFocus) main.focus();
  document.querySelector('#account-refresh')?.addEventListener('click', () => { void accountSession.load(); });
  document.querySelector('#workspace-retry')?.addEventListener('click', () => { void workspace.load(accountSession.snapshot().workspaceId); });
  document.querySelector('#records-retry')?.addEventListener('click',()=>{void persistence.load(accountSession.snapshot().workspaceId);});
  document.querySelector('#save-retry')?.addEventListener('click',()=>{void persistence.retry();});
  for(const [id,kind] of [['more-projects','projects'],['more-saved','saved_work']])document.getElementById(id)?.addEventListener('click',()=>{void persistence.more(kind);});
  document.querySelector('#project-create')?.addEventListener('submit',event=>{event.preventDefault();const form=new FormData(event.currentTarget);void persistence.save('project.create',crypto.randomUUID(),0,{title:String(form.get('title')||'').trim()});});
  document.querySelectorAll('[data-project-rename]').forEach(button=>button.addEventListener('click',()=>{
    const row=persistence.snapshot().projects.find(r=>r.id===button.dataset.projectRename);
    const title=document.getElementById(`title-${row?.id}`)?.value.trim();if(row&&title)void persistence.save('project.update',row.id,row.version,{title});
  }));
  document.querySelectorAll('[data-record-delete]').forEach(button=>button.addEventListener('click',()=>{
    const [kind,id]=button.dataset.recordDelete.split(':');const row=(kind==='project'?persistence.snapshot().projects:persistence.snapshot().saved).find(r=>r.id===id);
    if(row)void persistence.save(`${kind}.delete`,id,row.version,{});
  }));
  document.querySelectorAll('[data-saved-open]').forEach(button=>button.addEventListener('click',()=>{void persistence.open(button.dataset.savedOpen);}));
  document.querySelector('#saved-rename')?.addEventListener('submit',event=>{event.preventDefault();const row=persistence.snapshot().selected;const form=new FormData(event.currentTarget);if(row)void persistence.save('saved.update',row.id,row.version,{title:String(form.get('title')||'').trim(),payload:row.payload});});
  document.querySelector('#save-investigation')?.addEventListener('submit',event=>{event.preventDefault();const form=new FormData(event.currentTarget),payload=accountPayload(chat.snapshot().turns);
    if(payload)void persistence.save('saved.create',crypto.randomUUID(),0,{title:String(form.get('title')||'').trim(),project_id:form.get('project'),payload});
  });
  document.querySelector('#profile-edit')?.addEventListener('submit',event=>{event.preventDefault();const form=new FormData(event.currentTarget),profile=workspace.snapshot().data?.profile;
    if(profile)void persistence.save('profile.update',null,profile.version,{display_name:String(form.get('display_name')||''),preferences:{default_section:form.get('default_section'),reduced_motion:form.get('reduced_motion')==='on'}});
  });
  document.querySelector('#account-logout')?.addEventListener('click', () => {
    workspace.leave();
    persistence.leave();
    activeHistoryId = null; chat.clear(); monitoring.setActive(false); api.disconnect('demo');
    void accountSession.logout();
  });
  document.querySelector('#auth-form')?.addEventListener('submit', event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void auth.submit(route, { email: form.get('email'), password: form.get('password'), confirmation: form.get('confirmation') });
  });
  document.querySelector('#auth-retry')?.addEventListener('click', () => { void auth.load(); });
  document.querySelector('#connect-live')?.addEventListener('click', () => {
    activeHistoryId = null; monitoring.setActive(false); chat.setMode('live'); void api.connect();
  });
  for (const [id, mode] of [['use-demo', 'demo'], ['disconnect-api', 'disconnected']]) {
    document.getElementById(id)?.addEventListener('click', () => {
      activeHistoryId = null; monitoring.setActive(false); api.disconnect(mode); chat.setMode(mode === 'demo' ? 'demo' : 'live');
    });
  }
  if (route === 'dashboard') {
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
  for (const [id, getState] of [
    ['export-investigation', () => chat.snapshot()],
    ['export-saved-investigation', () => { const state = persistence.snapshot(); return { mode: 'demo', pending: state.pending, turns: state.selected?.payload.turns }; }],
  ]) document.getElementById(id)?.addEventListener('click', () => {
    try {
      downloadInvestigation(getState());
      document.querySelector('#announcement').textContent = 'Markdown report download requested. Saved history is unchanged.';
    } catch {
      document.querySelector('#announcement').textContent = 'Report unavailable. Complete the conversation and try again.';
    }
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
    window.location.hash = root === 'workspace' ? '/workspace/demo-chat' : '/chat';
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
      openSourceTarget(target);
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
  monitoring.setActive(contentRoute() === 'monitoring' && api.snapshot().mode === 'demo' && !document.hidden);
  if (!document.hidden && contentRoute() === 'monitoring') render();
});

function refreshHistory() {
  if (document.hidden) return;
  const route = contentRoute();
  if (activeHistoryId && !history.get(activeHistoryId)) { activeHistoryId = null; chat.clear(); }
  if (route === 'history') render();
}
window.addEventListener('storage', event => {
  if (event.key === HISTORY_KEY || event.key === null) refreshHistory();
});
setInterval(refreshHistory, 60000);

let previousRoot = routeFromHash(window.location.hash);
window.addEventListener('hashchange', () => {
  const nextRoot = routeFromHash(window.location.hash);
  const enteringClient = nextRoot === 'workspace' && previousRoot !== 'workspace';
  previousRoot = nextRoot;
  auth.leave();
  accountSession.leave();
  workspace.leave();
  persistence.leave();
  if (enteringClient) {
    activeHistoryId = null; api.disconnect('demo'); chat.setMode('demo');
  }
  render(true);
  if (isAuthRoute()) void auth.load();
  if (routeFromHash(window.location.hash) === 'workspace') void accountSession.load();
});
render();
if (isAuthRoute()) void auth.load();
if (routeFromHash(window.location.hash) === 'workspace') void accountSession.load();
