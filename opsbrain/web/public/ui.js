import { HISTORY_TTL } from './history.js';
import { DEMO_FIXTURE, DEMO_STATES, demoState } from './demo.js';
import { CHAT_SCENARIOS } from './chat.js';
import { METRICS, MONITORING_RANGES, MONITORING_SCENARIOS } from './monitoring.js';

export const ROUTES = Object.freeze([
  { id: 'home', title: 'Home', icon: 'book' },
  { id: 'dashboard', title: 'Overview', icon: 'grid' },
  { id: 'chat', title: 'Ask OpsBrain', icon: 'chat' },
  { id: 'monitoring', title: 'Monitoring', icon: 'pulse' },
  { id: 'history', title: 'History', icon: 'clock' },
  { id: 'components', title: 'Interface kit', icon: 'layers' },
]);

export const AGENTS = Object.freeze([
  { name: 'RAG', subtitle: 'Runbooks & knowledge', icon: 'book', color: 'lime' },
  { name: 'Monitoring', subtitle: 'Metrics & signals', icon: 'pulse', color: 'blue' },
  { name: 'Infra', subtitle: 'Infrastructure context', icon: 'layers', color: 'purple' },
  { name: 'Code', subtitle: 'Changes & delivery', icon: 'code', color: 'peach' },
]);

const paths = {
  grid: '<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="15" y="3" width="6" height="6" rx="1"/><rect x="3" y="15" width="6" height="6" rx="1"/><rect x="15" y="15" width="6" height="6" rx="1"/>',
  chat: '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5A8.5 8.5 0 0 1 10.5 3h2a8.5 8.5 0 0 1 8.5 8.5Z"/><path d="M7 10h10M7 14h6"/>',
  pulse: '<path d="M2 12h5l3-7 4 14 3-7h5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  layers: '<path d="m12 3 10 6-10 6L2 9Zm-9 11 9 5 9-5M3 18l9 5 9-5"/>',
  book: '<path d="M12 5v15M3 4h5a4 4 0 0 1 4 3 4 4 0 0 1 4-3h5v15h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3Z"/>',
  code: '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  shield: '<path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6Z"/><path d="m8 12 3 3 5-6"/>',
};

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}

export function icon(name, className = '') {
  return `<svg class="icon ${escapeHtml(className)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.grid}</svg>`;
}

export function badge(state, label = '') {
  if (!['live', 'demo', 'disconnected', 'pending'].includes(state)) throw new Error('Unknown data state');
  const title = label || ({ live: 'Live', demo: 'Demo', disconnected: 'Disconnected', pending: 'Coming next' }[state]);
  return `<span class="badge badge-${state}"><span class="status-dot" aria-hidden="true"></span>${escapeHtml(title)}</span>`;
}

export function routeFromHash(hash) {
  if (!hash || hash === '#' || hash === '#/') return 'home';
  const id = String(hash).replace(/^#\/?/, '').split(/[?\/]/)[0];
  return id === 'home' || ROUTES.some(route => route.id === id) ? id : 'dashboard';
}

export const LANDING_SECTIONS = Object.freeze(['specialists', 'workflow', 'preview-scope']);

export function landingSectionFromHash(hash) {
  if (routeFromHash(hash) !== 'home') return null;
  const section = new URLSearchParams(String(hash).split('?')[1] || '').get('section');
  return LANDING_SECTIONS.includes(section) ? section : null;
}

export function navigation(active) {
  return ROUTES.map(route => `<a href="#/${route.id}" ${active === route.id ? 'aria-current="page"' : ''}>${icon(route.icon)}<span>${route.title}</span>${route.ticket ? '<span class="nav-next">NEXT</span>' : ''}</a>`).join('');
}

export function agentCard(agent) {
  return `<article class="panel agent-card"><div class="agent-card-top"><span class="agent-icon ${escapeHtml(agent.color)}">${icon(agent.icon)}</span>${badge('disconnected')}</div><h3>${escapeHtml(agent.name)}</h3><p>${escapeHtml(agent.subtitle)}</p><div class="agent-card-footer"><span>Connection</span><span>Not configured</span></div></article>`;
}

export function emptyState(title, description, iconName = 'layers') {
  return `<div class="empty-state">${icon(iconName)}<h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p></div>`;
}

export function loadingState(label = 'Loading interface example') {
  return `<div class="loading-state" role="status" aria-label="${escapeHtml(label)}"><span class="skeleton wide" aria-hidden="true"></span><span class="skeleton" aria-hidden="true"></span><span class="skeleton short" aria-hidden="true"></span><span class="sr-only">${escapeHtml(label)}</span></div>`;
}

export function errorState(message) {
  return `<div class="notice error-notice" role="status">${icon('shield')}<div><strong>Connection unavailable</strong><p>${escapeHtml(message)}</p></div></div>`;
}

function heading(eyebrow, title, description, action = '') {
  return `<div class="page-heading"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="page-description">${description}</p></div>${action}</div>`;
}

export function demoAgentCard(agent, state) {
  state = demoState(state);
  const unavailable = state === 'partial' && agent.name === 'Code';
  const fixture = DEMO_FIXTURE.agents[agent.name];
  let summary = fixture?.summary || 'No sample context';
  let outcome = fixture?.outcome || 'No sample context';
  if (unavailable) { summary = 'Example code source unavailable'; outcome = 'Sample result unavailable'; }
  if (state === 'loading') { summary = 'Waiting for sample context'; outcome = 'Sample loading'; }
  if (state === 'empty') { summary = 'No sample context available'; outcome = 'Sample empty'; }
  if (state === 'error') { summary = 'Example request failed'; outcome = 'Sample error'; }
  if (state === 'disconnected') return agentCard(agent);
  return `<article class="panel agent-card"><div class="agent-card-top"><span class="agent-icon ${escapeHtml(agent.color)}">${icon(agent.icon)}</span>${badge('demo')}</div><h3>${escapeHtml(agent.name)}</h3><p>${escapeHtml(agent.subtitle)}</p><p class="sample-summary">${escapeHtml(summary)}</p><div class="agent-card-footer"><span>Demo outcome</span><span>${escapeHtml(outcome)}</span></div></article>`;
}

function demoContent(state) {
  if (state === 'loading') return `<div class="demo-state-content">${loadingState('Demo loading state; no request is in progress')}<p class="form-help">Illustrative loading state. Select another preview state to continue.</p></div>`;
  if (state === 'empty') return emptyState('No sample signals or activity', 'This demo illustrates a successful response with no records.', 'pulse');
  if (state === 'error') return `<div class="demo-state-content">${errorState('Demo error: the example request failed. No successful metrics or activity are shown.')}<a class="button secondary" href="#/dashboard?state=populated">Reset demo preview</a></div>`;
  if (state === 'disconnected') return emptyState('No backend connected', 'Choose a demo preview state to explore synthetic signals and activity. Use Connect live for the optional API adapter.', 'pulse');
  return `${state === 'partial' ? `<div class="notice error-notice">${icon('shield')}<div><strong>Demo partial availability</strong><p>The example Code source failed. Other sample results remain visible; no all-clear is inferred.</p></div></div>` : ''}
    <dl class="signal-grid">${DEMO_FIXTURE.signals.map(signal => `<div><dt>${escapeHtml(signal.label)} ${badge('demo')}</dt><dd>${escapeHtml(signal.value)}<p>${escapeHtml(signal.detail)}</p></dd></div>`).join('')}</dl>
    <div class="panel-heading"><h3>Example activity</h3>${badge('demo')}</div>
    <ul class="activity-list">${DEMO_FIXTURE.activity.filter(item => state !== 'partial' || item.agent !== 'Code').map(item => `<li><span class="small-label">${escapeHtml(item.agent)}</span><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.detail)}</p></li>`).join('')}</ul>`;
}

function dashboard(selectedState) {
  const state = demoState(selectedState);
  const label = DEMO_STATES.find(item => item.id === state).label;
  return `${heading('YOUR ENGINEER WORKSPACE', 'Less noise. More context.', 'Explore your workspace with clearly labelled sample context.', `<a class="button secondary" href="#/components">${icon('layers')} Interface kit</a>`)}
    <div class="notice connection-notice">${icon('shield')}<div><strong>Backend disconnected. Demo stays separate.</strong><p>No backend requests are made. All demo values are synthetic, fixed examples, never live health or metrics.</p></div>${badge('disconnected', 'Backend disconnected')}</div>
    <section class="panel demo-controls" aria-labelledby="demo-controls-title"><div><h2 id="demo-controls-title">Preview a dashboard state</h2><p id="demo-state-help">Changes affect this preview only. No questions are sent or saved.</p></div><div><label for="demo-state">Demo preview state</label><select id="demo-state" aria-describedby="demo-state-help">${DEMO_STATES.map(item => `<option value="${item.id}"${item.id === state ? ' selected' : ''}>${item.label}</option>`).join('')}</select></div></section>
    <p class="demo-state-label" role="status">Preview state: ${escapeHtml(label)}${state === 'disconnected' ? '' : ' · Demo only'}</p>
    <section aria-labelledby="agents-heading"><div class="section-heading"><h2 id="agents-heading">Your specialist agents <span class="count-label">04</span></h2><span>${state === 'disconnected' ? 'Connections not configured' : 'Synthetic context · not connection status'}</span></div><div class="agent-grid">${AGENTS.map(agent => demoAgentCard(agent, state)).join('')}</div></section>
    <div class="workspace-grid"><section class="panel"><div class="panel-heading"><h2>Signals at a glance</h2>${state === 'disconnected' ? badge('disconnected') : badge('demo')}</div>${demoContent(state)}</section><section class="panel"><div class="panel-heading"><h2>Continue your investigation</h2><span class="small-label">COMING NEXT</span></div><div class="principles"><div>${icon('chat')}<p><strong><a href="#/chat">Ask OpsBrain →</a></strong><span>Demo chat, citations and per-agent results</span></p></div><div>${icon('pulse')}<p><strong><a href="#/monitoring">Explore monitoring →</a></strong><span>Demo charts and refresh controls</span></p></div><div>${icon('clock')}<p><strong><a href="#/history">Conversation history →</a></strong><span>Browser-local history · 72-hour expiry</span></p></div></div></section></div>`;
}

function home(mode = 'demo') {
  const descriptions = [
    ['Find the runbook.', 'Retrieves relevant runbooks and checks answer citations against the retrieved context.', 'RAG needs an ingested knowledge base and configured embedding/database services.'],
    ['Read the signals.', 'Summarizes alerts, pod-health metrics and scrape targets from monitoring services.', 'Demo pod metrics are illustrative, not evidence of a real Kubernetes connection.'],
    ['Inspect the platform.', 'Provides AWS and Kubernetes context, plus existing Terraform state or plan-file inspection.', 'Real AWS/cluster acceptance is deferred. Terraform inspection does not create or apply a plan.'],
    ['Understand the change.', 'Brings together pull requests, commits, workflow status and deployment information.', 'A selected GitHub repository and appropriate credentials are still required.'],
  ];
  return `<div class="landing-intro"><span class="landing-kicker"><span class="status-dot" aria-hidden="true"></span> ENGINEER PREVIEW / BUILT FOR TWO</span><nav class="landing-links" aria-label="About OpsBrain"><a href="#/home?section=specialists">The agents</a><a href="#/home?section=workflow">How it works</a><a href="#/home?section=preview-scope">Preview scope</a></nav></div>
    <section class="landing-hero" aria-labelledby="landing-title">
      <div class="landing-hero-copy"><p class="eyebrow">OPERATIONS HAVE A STORY. FIND YOURS.</p><h1 id="landing-title">Connect the dots.<br><span>Understand the why.</span></h1><p class="landing-lede">OpsBrain brings runbooks, monitoring, infrastructure and code into one conversation—so you can investigate a problem without losing the bigger picture.</p><div class="button-row"><a class="button primary" href="#/dashboard">Open engineer dashboard ${icon('arrow')}</a><a class="button secondary" href="#/home?section=workflow">See how it works</a></div><p class="landing-disclosure">Local UI preview. ${mode === 'live' ? 'API connected; agent availability varies.' : 'No backend connected.'} Not deployed or access-protected yet.</p></div>
      <div class="question-map" aria-label="Illustration of an example question and four specialist perspectives; no query is executed"><div class="question-map-top"><span class="small-label">A QUESTION, FOUR PERSPECTIVES</span>${badge('demo', 'Illustration only')}</div><blockquote>“Why is the website slow?”</blockquote><p class="question-map-caption">Example question · not executed</p><div class="map-connector" aria-hidden="true"></div><div class="perspective-grid">${AGENTS.map(agent => `<div class="perspective-node"><span class="agent-icon ${agent.color}">${icon(agent.icon)}</span><strong>${agent.name}</strong><span>${agent.subtitle}</span></div>`).join('')}</div><div class="map-outcome">${icon('layers')}<div><strong>One answer, with context</strong><span>Sources and per-agent outcomes, not a guessed all-clear.</span></div></div></div>
    </section>
    <section class="landing-section" id="specialists" tabindex="-1" aria-labelledby="specialists-title"><div class="landing-section-heading"><div><p class="eyebrow">THE SPECIALISTS</p><h2 id="specialists-title">Different lenses. A clearer picture.</h2></div><p>Each agent has a specific job.<br>The orchestrator brings their context together.</p></div><div class="specialist-grid">${AGENTS.map((agent, index) => `<article class="panel specialist-card"><div class="specialist-card-top"><span class="agent-icon ${agent.color}">${icon(agent.icon)}</span><span class="small-label">0${index + 1} / ${agent.name}</span></div><h3>${descriptions[index][0]}</h3><p>${descriptions[index][1]}</p><div class="specialist-boundary">${descriptions[index][2]}</div></article>`).join('')}</div></section>
    <section class="landing-section workflow-section" id="workflow" tabindex="-1" aria-labelledby="workflow-title"><div class="landing-section-heading"><div><p class="eyebrow">FROM QUESTION TO CONTEXT</p><h2 id="workflow-title">Less tool-hopping.<br>More understanding.</h2></div><p>The implemented backend flow, when connected.<br>This page does not run queries.</p></div><ol class="workflow-steps"><li><span class="step-number">01</span><div><h3>Ask the question</h3><p>The orchestrator selects the relevant agents. Model routing has a keyword fallback.</p></div></li><li><span class="step-number">02</span><div><h3>Gather the perspectives</h3><p>Selected agents run in parallel. A failed agent does not erase another agent’s useful context.</p></div></li><li><span class="step-number">03</span><div><h3>See the whole answer</h3><p>Answers retain sources and per-agent outcomes. Partial availability is reported, not hidden.</p></div></li></ol></section>
    <section class="landing-section" id="preview-scope" tabindex="-1" aria-labelledby="scope-title"><div class="landing-section-heading"><div><p class="eyebrow">HONEST ABOUT THE STARTING POINT</p><h2 id="scope-title">A small preview.<br>A deliberate foundation.</h2></div><p>For Rifat and Jeffin to build and review together.<br>Not a public production service.</p></div><div class="scope-grid"><article class="panel scope-panel"><span class="small-label">BACKEND IMPLEMENTED</span><h3>The engine behind the interface</h3><ul><li>Multi-agent routing, parallel queries and aggregation.</li><li>Groq chat roles with unchanged Gemini embeddings.</li><li>Sources, partial failures and deterministic fallbacks.</li><li>HTTP by default; Kafka through an explicit override.</li></ul><p>Implemented does not mean every external backend is configured or production deployment is accepted.</p></article><article class="panel scope-panel"><span class="small-label">FRONTEND TODAY</span><h3>Know what you are looking at</h3><ul><li>Landing page, navigation and dashboard foundation.</li><li>Agent connections shown as Disconnected.</li><li>Labelled dashboard states, demo chat and monitoring charts are available.</li><li>Demo history saves locally for 72 hours. Live API queries are optional.</li></ul><p>Demo questions stay in this browser. Live queries require an explicit API connection; no account signup or operational changes are offered.</p></article></div><div class="notice landing-access-note">${icon('shield')}<div><strong>Two engineers. Read-only intent. No public exposure.</strong><p>Hosting in OPU-91 must restrict access to your two approved email identities and independently protect any connected API. Until then, use this preview on localhost only.</p></div></div></section>
    <section class="landing-cta" aria-labelledby="cta-title"><div><p class="eyebrow">START WITH A CLEARER WORKSPACE</p><h2 id="cta-title">Make room for the signal.</h2><p>Explore the interface. The integrations come next.</p></div><a class="button primary" href="#/dashboard">Open engineer dashboard ${icon('arrow')}</a></section>`;
}

// Plain text only. Source numbers become local focus buttons, never HTML or URLs.
export function citedText(text, sources, prefix) {
  return escapeHtml(text).replace(/\[(\d+)\]/g, (match, number) => {
    const index = Number(number);
    if (index < 1 || index > sources.length) return match;
    return `<button type="button" class="citation" data-source-target="${escapeHtml(prefix)}-${index}" aria-label="Show source ${index}">[${index}]</button>`;
  });
}

export function chatResponse(response, turnIndex, mode = 'demo') {
  const prefix = `chat-source-${turnIndex}`;
  const labels = { ok: 'Complete', partial: 'Partial availability', error: 'Unavailable' };
  return `<section class="chat-answer" aria-labelledby="chat-answer-${turnIndex}"><div class="chat-answer-heading"><h3 id="chat-answer-${turnIndex}" tabindex="-1">${mode === 'live' ? 'API answer' : 'Example answer'}</h3>${badge(mode === 'live' ? 'live' : 'demo', `${mode === 'live' ? 'Live' : 'Demo'} · ${labels[response.status] || 'Unavailable'}`)}</div><p class="chat-text">${citedText(response.answer, response.sources, prefix)}</p>
    ${response.sources.length ? `<h4>${mode === 'live' ? 'API sources' : 'Example sources'}</h4><ol class="chat-sources">${response.sources.map((source, index) => `<li id="${prefix}-${index + 1}" tabindex="-1">${escapeHtml(source)} <span class="small-label">${mode === 'live' ? 'API SOURCE' : 'SYNTHETIC SOURCE'}</span></li>`).join('')}</ol>` : '<p class="form-help">No sources available for this response.</p>'}
    <h4>Per-agent results</h4><div class="chat-agent-results">${response.results.map(result => {
      const agent = AGENTS.find(item => item.name.toLowerCase() === result.agent);
      return `<details class="chat-agent-result"><summary><span>${escapeHtml(agent?.name || result.agent)}</span><span>${escapeHtml(result.status === 'ok' ? (mode === 'live' ? 'Result ready' : 'Sample result ready') : result.status === 'timeout' ? (mode === 'live' ? 'Timeout' : 'Sample timeout') : (mode === 'live' ? 'Unavailable' : 'Sample unavailable'))}</span></summary><p class="chat-text">${result.status === 'ok' ? citedText(result.answer, response.sources, prefix) : escapeHtml(result.error?.message || 'No context available')}</p>${result.status === 'ok' ? `<ul class="agent-source-list">${result.sources.map(source => `<li>${escapeHtml(source)}</li>`).join('')}</ul>` : ''}</details>`;
    }).join('') || '<p class="form-help">No agent results available.</p>'}</div></section>`;
}

function chatPage(state = { turns: [], pending: false, validation: '', draft: '', scenario: 'ok' }, historyState) {
  return `${heading('ASK OPSBRAIN', 'A question. Four perspectives.', 'Explore answers, sources and agent outcomes in a demo conversation.')}
    ${storageNotice(historyState)}
    <div class="notice connection-notice">${icon('shield')}<div><strong>Demo conversation · backend disconnected</strong><p>Your question stays in this browser. The selected scenario returns a fixed example, independent of your question. No model or backend is called.</p></div>${badge('demo')}</div>
    <section class="panel chat-conversation" aria-labelledby="chat-conversation-title"><div class="panel-heading"><h2 id="chat-conversation-title">Demo conversation</h2><button type="button" class="button secondary" id="clear-chat"${state.turns.length ? '' : ' disabled'}>New conversation</button></div>
    <div id="chat-turns" aria-busy="${state.pending}">${state.turns.length ? state.turns.map((turn, index) => `<article class="chat-turn"><div class="chat-question"><h3>Your question</h3><p class="chat-text">${escapeHtml(turn.question)}</p></div>${turn.response ? chatResponse(turn.response, index, turn.mode || state.mode) : loadingState('Preparing a fixed demo answer; no backend request')}</article>`).join('') : emptyState('Start with a question', 'Try “Why is the website slow?” to explore a fixed example. This preview does not investigate your systems.', 'chat')}</div></section>
    <form id="chat-form" class="panel chat-composer" novalidate><label for="chat-question">Your question</label><textarea id="chat-question" name="question" rows="3" maxlength="2000" required aria-describedby="chat-help chat-validation"${state.pending ? ' disabled' : ''} placeholder="Why is the website slow?">${escapeHtml(state.draft)}</textarea><p id="chat-help" class="form-help">5–2000 characters. Enter adds a new line. Completed conversations save locally for 72 hours. No questions are sent to a backend.</p><div class="chat-composer-actions"><div><label for="chat-scenario">Demo response scenario</label><select id="chat-scenario" name="scenario"${state.pending ? ' disabled' : ''}>${CHAT_SCENARIOS.map(item => `<option value="${item.id}"${item.id === state.scenario ? ' selected' : ''}>${item.label}</option>`).join('')}</select></div><button class="button primary" type="submit"${state.pending ? ' disabled' : ''}>${state.pending ? 'Preparing demo…' : 'Show demo answer'}</button></div><p id="chat-validation" class="form-result" role="status">${escapeHtml(state.validation)}</p><p class="form-help">Up to 20 questions per conversation. New conversation resets this chat and keeps saved history. Delete saved conversations from History.</p></form>`;
}

function storageNotice(state) {
  if (!state) return '';
  return `<p class="history-storage-note" role="status">${escapeHtml(state.warning || (state.persistent ? 'Completed demo conversations save in this browser for 72 hours after creation. No server sync or account protection.' : 'History is available in page memory only.'))}</p>`;
}

function historyPage(state = { records: [], persistent: true, warning: '' }) {
  return `${heading('CONVERSATION HISTORY', 'Keep the context.', 'Reopen a saved demo conversation or remove it from this browser.')}
    ${storageNotice(state)}<div class="notice connection-notice">${icon('clock')}<div><strong>Local history · 72-hour expiry</strong><p>Expiry is measured from creation and is not extended by reopening or continuing. Expired records are removed on access and while this page is active. This browser must run to clean up stored data.</p></div>${badge('demo')}</div>
    <section class="panel" aria-labelledby="history-heading"><div class="panel-heading"><h2 id="history-heading">Saved conversations <span class="count-label">${state.records.length} / 20</span></h2><button id="clear-history" class="button secondary" type="button"${state.records.length ? '' : ' disabled'}>Delete all history</button></div>
    ${state.records.length ? `<ul class="history-list">${state.records.map(record => `<li><div><h3>${escapeHtml(record.turns[0].question.slice(0, 120))}</h3><p>${record.turns.length} question${record.turns.length === 1 ? '' : 's'} · Demo only</p><p>Created <time datetime="${new Date(record.createdAt).toISOString()}">${new Date(record.createdAt).toISOString()}</time><br>Expires <time datetime="${new Date(record.createdAt + HISTORY_TTL).toISOString()}">${new Date(record.createdAt + HISTORY_TTL).toISOString()}</time></p></div><div class="button-row"><button type="button" class="button primary" data-open-history="${escapeHtml(record.id)}" aria-label="Open conversation: ${escapeHtml(record.turns[0].question.slice(0, 120))}">Open in chat</button><button type="button" class="button secondary" data-delete-history="${escapeHtml(record.id)}" aria-label="Delete conversation: ${escapeHtml(record.turns[0].question.slice(0, 120))}">Delete</button></div></li>`).join('')}</ul>` : emptyState('No saved conversations', 'Completed demo answers appear here. Conversations expire after 72 hours.', 'clock')}
    </section><p class="form-help">History belongs to this browser and address. Anyone using the same browser profile can read it. Only the latest 20 conversations are retained.</p><a href="#/chat" class="button secondary">Open demo chat ${icon('arrow')}</a>`;
}

export function metricChart(metric, points) {
  const valid = Array.isArray(points) && points.length >= 2 && points.every(point => Number.isFinite(point.value) && point.value >= 0 && point.value <= metric.maximum && Number.isFinite(point.minutesAgo) && point.minutesAgo >= 0);
  if (!valid) return emptyState('Metric unavailable', 'No valid samples for this metric. Missing values are not zero.', 'pulse');
  const id = `monitoring-${metric.id}`;
  const coordinates = points.map((point, index) => `${40 + index * 520 / (points.length - 1)},${180 - point.value * 160 / metric.maximum}`).join(' ');
  const latest = points.at(-1).value;
  return `<p class="metric-value">${escapeHtml(latest)}<span>${escapeHtml(metric.unit)}</span><small>Latest synthetic sample</small></p>
    <svg class="metric-chart" viewBox="0 0 600 225" role="img" aria-labelledby="${id}-title ${id}-description"><title id="${id}-title">${escapeHtml(metric.title)} · Demo</title><desc id="${id}-description">Synthetic samples from ${points[0].minutesAgo} minutes ago to now. Latest value ${latest} ${escapeHtml(metric.unit)}. Exact values are in the sample table below.</desc><path class="chart-grid" d="M40 20H560 M40 100H560 M40 180H560"/><text x="4" y="24">${metric.maximum}</text><text x="4" y="184">0</text><polyline class="chart-line" points="${coordinates}"/><text x="40" y="210">−${points[0].minutesAgo} min</text><text x="560" y="210" text-anchor="end">Now</text></svg>
    <details class="chart-samples"><summary>View sample values</summary><table><caption>${escapeHtml(metric.title)} · synthetic samples (${escapeHtml(metric.unit)})</caption><thead><tr><th scope="col">Relative time</th><th scope="col">Value (${escapeHtml(metric.unit)})</th></tr></thead><tbody>${points.map(point => `<tr><th scope="row">${point.minutesAgo === 0 ? 'Now' : `${point.minutesAgo} min ago`}</th><td>${point.value}</td></tr>`).join('')}</tbody></table></details>`;
}

function monitoringPage(state = { scenario: 'disconnected', range: '15m', pending: false, samples: null, refreshedAt: null, auto: false }) {
  let content;
  if (state.pending) content = `<section class="panel monitoring-state">${loadingState('Refreshing synthetic monitoring samples; no backend request')}</section>`;
  else if (state.scenario === 'disconnected') content = `<section class="panel">${emptyState('No monitoring backend connected', 'Choose a demo scenario to explore synthetic charts. No Prometheus or cluster is queried.', 'pulse')}</section>`;
  else if (state.scenario === 'error') content = `<section class="panel monitoring-state">${errorState('Demo monitoring error. No successful charts are shown. Refresh retries the selected demo scenario; choose Populated to view samples.')}</section>`;
  else if (state.scenario === 'empty' || !state.samples) content = `<section class="panel">${emptyState('No samples in this window', 'This preview has no chart values. Missing samples are not a healthy zero.', 'pulse')}</section>`;
  else content = `${state.scenario === 'partial' ? `<div class="notice error-notice monitoring-partial">${icon('shield')}<div><strong>Demo partial availability</strong><p>Latency samples are unavailable. CPU and memory remain visible; no all-clear is inferred.</p></div></div>` : ''}<div class="monitoring-grid">${METRICS.map(metric => `<section class="panel metric-panel" aria-labelledby="metric-${metric.id}"><div class="panel-heading"><h2 id="metric-${metric.id}">${metric.title}</h2>${badge('demo')}</div><div class="metric-body">${metricChart(metric, state.samples[metric.id])}</div></section>`).join('')}</div>`;
  return `${heading('MONITORING', 'Read the signals.', 'Explore synthetic trends with explicit availability and refresh controls.')}
    <div class="notice connection-notice">${icon('shield')}<div><strong>Demo monitoring · backend disconnected</strong><p>All chart values are synthetic. Refresh alternates two fixed sample sets; it does not retrieve live metrics.</p></div>${badge('disconnected', 'Backend disconnected')}</div>
    <section class="panel monitoring-controls" aria-label="Monitoring preview controls"><div><label for="monitoring-scenario">Demo scenario</label><select id="monitoring-scenario">${MONITORING_SCENARIOS.map(item => `<option value="${item.id}"${item.id === state.scenario ? ' selected' : ''}>${item.label}</option>`).join('')}</select></div><div><label for="monitoring-range">Time window</label><select id="monitoring-range">${MONITORING_RANGES.map(item => `<option value="${item.id}"${item.id === state.range ? ' selected' : ''}>${item.label}</option>`).join('')}</select></div><button type="button" id="monitoring-refresh" class="button primary"${state.pending || state.scenario === 'disconnected' ? ' disabled' : ''}>${state.pending ? 'Refreshing demo…' : 'Refresh demo'}</button><label class="auto-refresh-label"><input id="monitoring-auto" type="checkbox"${state.auto ? ' checked' : ''}${state.scenario === 'disconnected' ? ' disabled' : ''}> Auto-refresh demo (30s)</label></section>
    <p class="monitoring-refresh-note" role="status">${state.pending ? 'Preparing a new synthetic snapshot…' : state.refreshedAt ? `Demo generated at ${escapeHtml(state.refreshedAt)} · not a backend observation time` : 'No demo snapshot generated yet.'} Auto-refresh stops when you leave this page or hide the tab.</p><div id="monitoring-results" aria-busy="${state.pending}">${content}</div>`;
}

function components() {
  return `${heading('THE INTERFACE KIT', 'One visual language.', 'Small, reusable building blocks for the work ahead.')}
    <div class="component-grid"><section class="panel component-panel"><h2>Data provenance</h2><p>Examples only. These badges do not report a real connection.</p><div class="badge-row">${badge('live')}${badge('demo')}${badge('disconnected')}${badge('pending')}</div></section><section class="panel component-panel"><h2>Actions</h2><p>A clear hierarchy, with visible keyboard focus.</p><div class="button-row"><button class="button primary" type="button" data-preview-action>Preview interaction ${icon('arrow')}</button><a class="button secondary" href="#/dashboard">Back to workspace</a><button class="button secondary" disabled>Not available</button></div></section><section class="panel component-panel"><h2>Input</h2><form id="draft-form"><label for="draft">Question draft <span class="small-label">UI EXAMPLE</span></label><textarea id="draft" name="draft" rows="3" maxlength="2000" required aria-describedby="draft-help" placeholder="What would you like to understand?"></textarea><p id="draft-help" class="form-help">Interface test only. Not saved, sent to an agent or processed by a model.</p><button class="button primary" type="submit">Check draft ${icon('arrow')}</button><p id="draft-result" class="form-result" role="status" aria-live="polite"></p></form></section><section class="panel component-panel"><h2>Loading</h2><p>Illustrative loading state, not a pending network call.</p>${loadingState()}</section><section class="panel component-panel"><h2>Empty</h2>${emptyState('No conversations yet', 'Completed demo conversations appear in History.', 'chat')}</section><section class="panel component-panel"><h2>Error</h2>${errorState('This is an example error. A failed connection must never look like healthy demo data.')}</section></div>`;
}

function connectionControls(state) {
  const mode = state.mode;
  return `<section class="panel connection-controls" aria-label="Data connection controls"><div>${badge(mode === 'live' ? 'live' : mode === 'demo' ? 'demo' : 'disconnected', mode === 'live' ? 'Live API connected' : mode === 'demo' ? 'Demo mode' : mode === 'connecting' ? 'Connecting…' : 'Disconnected')}<p role="status">${escapeHtml(state.message || (mode === 'demo' ? 'Demo data only. Connect live explicitly to query your local backend.' : 'Live data is unavailable until the API connection succeeds.'))}</p></div><div class="button-row"><button class="button primary" id="connect-live" type="button"${mode === 'connecting' || mode === 'live' ? ' disabled' : ''}>Connect live</button><button class="button secondary" id="use-demo" type="button"${mode === 'demo' ? ' disabled' : ''}>Use demo</button><button class="button secondary" id="disconnect-api" type="button"${mode === 'disconnected' ? ' disabled' : ''}>Disconnect</button></div><p class="form-help">Switching modes starts a new chat and stops demo refresh. Live conversations stay in page memory; saved History contains demo conversations only.</p></section>`;
}

function liveChatPage(state, connection) {
  const ready = connection.mode === 'live';
  const pending = state.pending;
  return `${heading('ASK OPSBRAIN', 'Investigate with the API.', 'Answers, sources and per-agent outcomes from your connected orchestrator.')}
    <div class="notice connection-notice">${icon('shield')}<div><strong>Live query mode</strong><p>Submitting sends your question to the configured local orchestrator. No synthetic answer is substituted on failure. Conversations are not saved in browser History.</p></div>${badge(ready ? 'live' : 'disconnected')}</div>
    <section class="panel chat-conversation"><div class="panel-heading"><h2>Live conversation</h2><button class="button secondary" type="button" id="clear-chat">New conversation</button></div><div aria-busy="${pending}">${state.turns.length ? state.turns.map((turn, index) => `<article class="chat-turn"><div class="chat-question"><h3>Your question</h3><p class="chat-text">${escapeHtml(turn.question)}</p></div>${turn.response ? chatResponse(turn.response, index, 'live') : loadingState('Waiting for live API answer')}</article>`).join('') : emptyState('Ask your connected system', ready ? 'Submit a question to receive API context. Connection health is not proof that every agent is available.' : 'Connect live before submitting a question.', 'chat')}</div></section>
    <form id="chat-form" class="panel chat-composer" novalidate><label for="chat-question">Your question</label><textarea id="chat-question" name="question" rows="3" maxlength="2000" aria-describedby="chat-help chat-validation"${pending || !ready ? ' disabled' : ''}>${escapeHtml(state.draft)}</textarea><input type="hidden" name="scenario" value="ok"><p class="form-help" id="chat-help">5–2000 characters. The API may use configured model providers and operational services. Enter adds a new line.</p><button class="button primary" type="submit"${pending || !ready ? ' disabled' : ''}>${pending ? 'Waiting for API…' : 'Ask live API'}</button><p id="chat-validation" class="form-result" role="status">${escapeHtml(state.validation)}</p></form>`;
}

function liveMonitoringPage(state) {
  const data = state.monitoring;
  return `${heading('LIVE MONITORING', 'Read the current context.', 'Read-only snapshots from the monitoring API. Backend demo exporters may supply these values.')}
    <button type="button" class="button primary" id="live-monitoring-refresh"${state.pending || state.mode !== 'live' ? ' disabled' : ''}>${state.pending ? 'Refreshing API…' : 'Refresh live snapshots'}</button><p class="form-help">CPU, memory and latency charts are demo-only. Live snapshot refresh is manual. No demo values appear in this view.</p>
    <div aria-busy="${state.pending}">${state.pending ? loadingState('Fetching live monitoring snapshots') : data ? `<p class="form-help">Retrieved at ${escapeHtml(data.observedAt)} · retrieval time, not metric observation time</p><div class="monitoring-grid"><section class="panel"><div class="panel-heading"><h2>Alerts</h2>${badge(data.alerts ? 'live' : 'disconnected')}</div>${data.alerts ? `<dl class="principles"><div><dt>Total alerts</dt><dd>${data.alerts.total}</dd></div><div><dt>Active</dt><dd>${data.alerts.active}</dd></div><div><dt>Suppressed</dt><dd>${data.alerts.suppressed}</dd></div></dl>` : emptyState('Alerts unavailable', 'The alert request failed or returned invalid data.', 'pulse')}</section><section class="panel"><div class="panel-heading"><h2>Pods</h2>${badge(data.pods ? 'live' : 'disconnected')}</div>${data.pods ? `<div class="metric-body"><p>Total pods: ${data.pods.total}</p><ul>${data.pods.phases.map(item => `<li>${escapeHtml(item.phase)}: ${item.total}</li>`).join('')}</ul></div>` : emptyState('Pod health unavailable', 'The pod request failed or returned invalid data.', 'layers')}</section></div>` : emptyState('No live snapshot yet', 'Connect live, then refresh. A successful connection does not establish monitoring availability.', 'pulse')}</div>`;
}

export function renderPage(id, options = {}) {
  const connection = options.connectionState;
  let page;
  if (connection && connection.mode !== 'demo' && id === 'chat') page = { title: 'Ask OpsBrain', html: liveChatPage(options.chatState || { turns: [], pending: false, draft: '', validation: '' }, connection) };
  else if (connection && connection.mode !== 'demo' && id === 'monitoring') page = { title: 'Monitoring', html: liveMonitoringPage(connection) };
  else if (connection && connection.mode !== 'demo' && id === 'dashboard') page = { title: 'Overview', html: `${heading('ENGINEER WORKSPACE', 'Your API workspace.', 'Agent outcomes appear with each answer. No dashboard health is inferred.')}<div class="button-row"><a class="button primary" href="#/chat">Ask OpsBrain</a><a class="button secondary" href="#/monitoring">Monitoring snapshots</a></div>` };
  else page = renderContent(id, options);
  return { ...page, html: (connection ? connectionControls(connection) : '') + page.html };
}

function renderContent(id, options = {}) {
  if (id === 'home') return { title: 'Home', html: home(options.connectionState?.mode) };
  if (id === 'chat') return { title: 'Ask OpsBrain', html: chatPage(options.chatState, options.historyState) };
  if (id === 'history') return { title: 'History', html: historyPage(options.historyState) };
  if (id === 'monitoring') return { title: 'Monitoring', html: monitoringPage(options.monitoringState) };
  if (id === 'components') return { title: 'Interface kit', html: components() };
  const route = ROUTES.find(item => item.id === id);
  if (route?.ticket) return { title: route.title, html: `${heading('NEXT IN THE WORKSPACE', route.title, 'A home for this feature, without pretending it is built yet.')}<section class="panel welcome-panel">${badge('pending', route.ticket)}${emptyState('The foundation is here.', `${route.title} functionality belongs to ${route.ticket}. No backend or demo responses are connected yet.`, route.icon)}<a href="#/dashboard" class="button secondary">${icon('arrow')} Back to overview</a></section>` };
  return { title: 'Overview', html: dashboard(options.dashboardState) };
}

export function validateDraft(value) {
  const text = String(value).trim();
  if (text.length > 2000) return 'Keep the draft within 2000 characters.';
  return text.length < 5 ? 'Please write at least five characters for a useful question.' : `Draft checked (${text.length} characters). Nothing was sent or saved.`;
}
