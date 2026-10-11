import { createMonitoring } from './monitoring.js';
import { createChat } from './chat.js';
import { demoStateFromHash } from './demo.js';
import { landingSectionFromHash, navigation, renderPage, routeFromHash, validateDraft } from './ui.js';

const main = document.querySelector('#main');
const nav = document.querySelector('#workspace-navigation');
const toggle = document.querySelector('.menu-toggle');
const chat = createChat({ onChange() {
  if (routeFromHash(window.location.hash) !== 'chat') return;
  render();
  const state = chat.snapshot();
  document.querySelector('#announcement').textContent = state.validation || (state.pending ? 'Preparing a fixed demo answer.' : state.turns.length ? 'Demo answer ready. Sources and per-agent results follow your question.' : 'Demo conversation cleared.');
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
  monitoring.setActive(route === 'monitoring' && !document.hidden);
  const page = renderPage(route, { dashboardState: demoStateFromHash(window.location.hash), chatState: chat.snapshot(), monitoringState: monitoring.snapshot() });
  nav.innerHTML = navigation(route);
  // Renderers contain trusted templates; all dynamic text is escaped in ui.js.
  main.innerHTML = page.html;
  main.classList.toggle('landing-page', route === 'home');
  document.querySelector('#breadcrumb').textContent = page.title;
  document.title = `${page.title} — OpsBrain`;
  toggle.setAttribute('aria-expanded', 'false');
  nav.classList.remove('is-open');
  if (moveFocus) main.focus();
  if (route === 'dashboard' && moveFocus) {
    document.querySelector('#demo-state')?.focus();
    document.querySelector('#announcement').textContent = `Dashboard preview: ${document.querySelector('#demo-state').selectedOptions[0].textContent}. Backend disconnected.`;
  }
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
    void chat.submit(form.get('question'), form.get('scenario'));
  });
  document.querySelector('#clear-chat')?.addEventListener('click', () => chat.clear());
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
  monitoring.setActive(routeFromHash(window.location.hash) === 'monitoring' && !document.hidden);
  if (!document.hidden && routeFromHash(window.location.hash) === 'monitoring') render();
});

window.addEventListener('hashchange', () => render(true));
render();
