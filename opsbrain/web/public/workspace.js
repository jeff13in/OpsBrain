export const WORKSPACE_SECTIONS = Object.freeze([
  { id: 'dashboard', title: 'Dashboard', icon: 'grid' },
  { id: 'tools', title: 'Software tools', icon: 'layers' },
  { id: 'projects', title: 'Projects & saved work', icon: 'book' },
  { id: 'activity', title: 'Recent activity', icon: 'clock' },
  { id: 'settings', title: 'Account settings', icon: 'shield' },
  { id: 'help', title: 'Help & support', icon: 'chat' },
]);
const demos = Object.freeze({ 'demo-chat': 'chat', 'demo-monitoring': 'monitoring', 'demo-history': 'history' });
export function workspaceSectionFromHash(hash) {
  const section = String(hash).replace(/^#\/?/, '').split('/')[1]?.split('?')[0];
  return WORKSPACE_SECTIONS.some(item => item.id === section) || Object.hasOwn(demos, section) ? section : 'dashboard';
}
export function workspaceDemoRoute(hash) { return demos[workspaceSectionFromHash(hash)] || null; }
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export function validateWorkspaceSummary(body, workspaceId) {
  if (!body || body.workspace?.id !== workspaceId || !uuid.test(workspaceId) || typeof body.workspace.name !== 'string'
    || !body.workspace.name.trim() || body.workspace.name.length > 120 || typeof body.profile?.display_name !== 'string'
    || body.profile.display_name.length > 120 || !Array.isArray(body.recent_projects) || body.recent_projects.length > 10
    || !['project_writes', 'preferences'].every(key => typeof body.capabilities?.[key] === 'boolean')
    || body.capabilities.activity !== false || body.capabilities.live_tools !== false) return null;
  if (body.capabilities.preferences && (!Number.isSafeInteger(body.profile.version) || body.profile.version < 1
    || !['dashboard','projects','tools'].includes(body.profile.preferences?.default_section) || typeof body.profile.preferences.reduced_motion !== 'boolean')) return null;
  const ids = new Set();
  for (const row of body.recent_projects) {
    if (!row || typeof row.id !== 'string' || !uuid.test(row.id) || ids.has(row.id) || typeof row.title !== 'string'
      || !row.title.trim() || row.title.length > 200 || typeof row.updated_at !== 'string' || row.updated_at.length > 64
      || !/(?:Z|[+-]\d\d:\d\d)$/.test(row.updated_at) || !Number.isFinite(Date.parse(row.updated_at))
      || !Number.isSafeInteger(row.version) || row.version < 1) return null;
    ids.add(row.id);
  }
  // Copy only permitted fields; extra provider/response metadata is discarded.
  return { workspace: { id: workspaceId, name: body.workspace.name }, profile: { display_name: body.profile.display_name,
    ...(body.capabilities.preferences ? {version:body.profile.version,preferences:{default_section:body.profile.preferences.default_section,reduced_motion:body.profile.preferences.reduced_motion}} : {}) },
    capabilities:{project_writes:body.capabilities.project_writes,preferences:body.capabilities.preferences,saved_work:body.capabilities.saved_work===true},
    recent_projects: body.recent_projects.map(({ id, title, updated_at, version }) => ({ id, title, updated_at, version })) };
}

export function createWorkspace({ fetcher = (...args) => globalThis.fetch(...args), onChange = () => {}, onUnauthorized = () => {}, timeoutMs = 10000 } = {}) {
  let state = { status: 'idle', workspaceId: null, data: null, message: '' };
  let generation = 0, controller;
  const snapshot = () => structuredClone(state);
  function leave() { generation++; controller?.abort(); state = { status: 'idle', workspaceId: null, data: null, message: '' }; }
  async function load(workspaceId) {
    leave();
    if (!uuid.test(workspaceId)) return;
    const current = generation;
    state = { status: 'loading', workspaceId, data: null, message: 'Loading your workspace…' }; onChange();
    const active = new AbortController(); controller = active;
    const timer = setTimeout(() => active.abort(), timeoutMs);
    try {
      const response = await fetcher(`/api/workspaces/${workspaceId}/summary`, { credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: active.signal });
      if (current !== generation) return;
      if ([401, 403].includes(response.status)) {
        leave(); onChange(); onUnauthorized(response.status === 401 ? '#/login' : '#/verification'); return;
      }
      if (response.status !== 200) throw new Error('Unavailable workspace');
      const text = await response.text();
      if (text.length > 16384) throw new Error('Oversized summary');
      const data = validateWorkspaceSummary(JSON.parse(text), workspaceId);
      if (!data) throw new Error('Invalid summary');
      if (current !== generation) return;
      state = { status: 'ready', workspaceId, data, message: 'Workspace loaded.' };
    } catch { if (current === generation) state = { status: 'error', workspaceId, data: null, message: 'Your workspace could not be loaded. Please try again.' }; }
    finally { clearTimeout(timer); if (current === generation) onChange(); }
  }
  return { snapshot, load, leave };
}
