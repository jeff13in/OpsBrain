export const ROUTES = Object.freeze([
  { id: 'dashboard', title: 'Overview', icon: 'grid' },
  { id: 'chat', title: 'Ask OpsBrain', icon: 'chat', ticket: 'OPU-87' },
  { id: 'monitoring', title: 'Monitoring', icon: 'pulse', ticket: 'OPU-88' },
  { id: 'history', title: 'History', icon: 'clock', ticket: 'OPU-89' },
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
  const id = String(hash).replace(/^#\/?/, '').split(/[?\/]/)[0];
  return id === 'home' || ROUTES.some(route => route.id === id) ? id : 'dashboard';
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

function dashboard() {
  return `${heading('YOUR ENGINEER WORKSPACE', 'Less noise. More context.', 'A clear starting point for understanding your operations.', `<a class="button secondary" href="#/components">${icon('layers')} Interface kit</a>`)}
    <div class="notice connection-notice">${icon('shield')}<div><strong>Nothing connected. Nothing assumed.</strong><p>This is the UI foundation. No backend requests are made, and no live health or metrics are reported.</p></div>${badge('disconnected', 'Backend disconnected')}</div>
    <section class="hero-panel"><div><p class="eyebrow">ONE WORKSPACE. FOUR PERSPECTIVES.</p><h2>Find the signal<br>in your operations.</h2><p>Runbooks, metrics, infrastructure and code.<br>A thoughtful workspace to bring them together.</p><a class="button primary" href="#/chat">Explore the chat layout ${icon('arrow')}</a></div><div class="constellation" aria-hidden="true"><span class="orbit orbit-one"></span><span class="orbit orbit-two"></span><span class="orbit-center">ob<span>.</span></span><span class="orbit-node node-book">${icon('book')}</span><span class="orbit-node node-pulse">${icon('pulse')}</span><span class="orbit-node node-layers">${icon('layers')}</span><span class="orbit-node node-code">${icon('code')}</span><span class="orbit-caption">CONTEXT, CONNECTED.</span></div></section>
    <section aria-labelledby="agents-heading"><div class="section-heading"><h2 id="agents-heading">Your specialist agents <span class="count-label">04</span></h2><span>Awaiting integration · OPU-86 / 90</span></div><div class="agent-grid">${AGENTS.map(agentCard).join('')}</div></section>
    <div class="workspace-grid"><section class="panel"><div class="panel-heading"><h2>Signals at a glance</h2><a href="#/monitoring" aria-label="Open monitoring layout">${icon('arrow')}</a></div>${emptyState('A little quiet, for now.', 'Monitoring charts and labelled demo metrics arrive in OPU-88.', 'pulse')}</section><section class="panel"><div class="panel-heading"><h2>Context you can trust</h2><span class="small-label">READ-ONLY</span></div><div class="principles"><div>${icon('book')}<p><strong>Sources, not guesses</strong><span>Citations stay alongside answers.</span></p></div><div>${icon('layers')}<p><strong>Every agent has a voice</strong><span>Partial results stay visible.</span></p></div><div>${icon('shield')}<p><strong>Honest about availability</strong><span>Live, Demo and Disconnected stay distinct.</span></p></div></div></section></div>`;
}

function home() {
  return `${heading('OPS BRAIN / ENGINEER PREVIEW', 'A little clarity goes a long way.', 'The start of your OpsBrain website, built for two engineers.')}
    <section class="panel welcome-panel"><span class="agent-icon lime">${icon('layers')}</span><h2>Your workspace is taking shape.</h2><p>The visual foundation is ready. The landing-page content, demo dashboard, chat and monitoring views are coming in the next tickets.</p><div class="button-row"><a class="button primary" href="#/dashboard">Open workspace ${icon('arrow')}</a><a class="button secondary" href="#/components">Explore components</a></div><div class="welcome-note">Local foundation only · Not deployed or access-protected yet</div></section>`;
}

function components() {
  return `${heading('THE INTERFACE KIT', 'One visual language.', 'Small, reusable building blocks for the work ahead.')}
    <div class="component-grid"><section class="panel component-panel"><h2>Data provenance</h2><p>Examples only. These badges do not report a real connection.</p><div class="badge-row">${badge('live')}${badge('demo')}${badge('disconnected')}${badge('pending')}</div></section><section class="panel component-panel"><h2>Actions</h2><p>A clear hierarchy, with visible keyboard focus.</p><div class="button-row"><button class="button primary" type="button" data-preview-action>Preview interaction ${icon('arrow')}</button><a class="button secondary" href="#/dashboard">Back to workspace</a><button class="button secondary" disabled>Not available</button></div></section><section class="panel component-panel"><h2>Input</h2><form id="draft-form"><label for="draft">Question draft <span class="small-label">UI EXAMPLE</span></label><textarea id="draft" name="draft" rows="3" maxlength="2000" required aria-describedby="draft-help" placeholder="What would you like to understand?"></textarea><p id="draft-help" class="form-help">Interface test only. Not saved, sent to an agent or processed by a model.</p><button class="button primary" type="submit">Check draft ${icon('arrow')}</button><p id="draft-result" class="form-result" role="status" aria-live="polite"></p></form></section><section class="panel component-panel"><h2>Loading</h2><p>Illustrative loading state, not a pending network call.</p>${loadingState()}</section><section class="panel component-panel"><h2>Empty</h2>${emptyState('No conversations yet', 'Chat history will arrive in OPU-89.', 'chat')}</section><section class="panel component-panel"><h2>Error</h2>${errorState('This is an example error. A failed connection must never look like healthy demo data.')}</section></div>`;
}

export function renderPage(id) {
  if (id === 'home') return { title: 'Home', html: home() };
  if (id === 'components') return { title: 'Interface kit', html: components() };
  const route = ROUTES.find(item => item.id === id);
  if (route?.ticket) return { title: route.title, html: `${heading('NEXT IN THE WORKSPACE', route.title, 'A home for this feature, without pretending it is built yet.')}<section class="panel welcome-panel">${badge('pending', route.ticket)}${emptyState('The foundation is here.', `${route.title} functionality belongs to ${route.ticket}. No backend or demo responses are connected yet.`, route.icon)}<a href="#/dashboard" class="button secondary">${icon('arrow')} Back to overview</a></section>` };
  return { title: 'Overview', html: dashboard() };
}

export function validateDraft(value) {
  const text = String(value).trim();
  if (text.length > 2000) return 'Keep the draft within 2000 characters.';
  return text.length < 5 ? 'Please write at least five characters for a useful question.' : `Draft checked (${text.length} characters). Nothing was sent or saved.`;
}
