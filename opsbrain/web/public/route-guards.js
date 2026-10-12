const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const unavailable = 'Workspace access is unavailable. Please try again later.';
export function safePostLoginDestination(value) {
  return ['#/workspace', '#/home'].includes(value) ? value : '#/workspace';
}

export function createProtectedSession({ fetcher = (...args) => globalThis.fetch(...args), onChange = () => {}, onRedirect = () => {}, timeoutMs = 10000 } = {}) {
  let state = { status: 'checking', workspaceId: null, message: 'Checking account access…' };
  let csrf = '', generation = 0, controller;
  const snapshot = () => ({ ...state });
  function leave() {
    generation++; controller?.abort(); csrf = '';
    state = { status: 'checking', workspaceId: null, message: 'Checking account access…' };
  }
  async function request(path, options = {}) {
    const active = new AbortController(); controller = active;
    const timer = setTimeout(() => active.abort(), timeoutMs);
    try {
      const response = await fetcher(path, { credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: active.signal, ...options });
      if (response.status !== 200) return { status: response.status };
      const text = await response.text();
      if (text.length > 8192) throw new Error('Oversized session response');
      return { status: 200, body: JSON.parse(text) };
    } finally { clearTimeout(timer); }
  }
  async function load() {
    leave(); const current = generation; onChange();
    try {
      const { status, body } = await request('/api/auth/session');
      if (current !== generation) return;
      if (status === 401 || (status === 200 && body?.authenticated === false)) {
        state = { status: 'anonymous', workspaceId: null, message: 'Log in to open your workspace.' };
      } else if (status === 403 || (status === 200 && body?.authenticated === true && body?.verified === false)) {
        state = { status: 'unverified', workspaceId: null, message: 'Verify your email to continue.' };
      } else {
        if (status !== 200 || body?.authenticated !== true || body?.verified !== true || !uuid.test(body.user_id)
          || !Array.isArray(body.workspace_ids) || body.workspace_ids.length < 1 || body.workspace_ids.length > 100
          || !body.workspace_ids.every(id => typeof id === 'string' && uuid.test(id))
          || typeof body.csrf_token !== 'string' || !/^[A-Za-z0-9_-]{32,256}$/.test(body.csrf_token)) throw new Error('Invalid session');
        csrf = body.csrf_token;
        state = { status: 'authorized', workspaceId: body.workspace_ids[0], message: 'Your account is verified.' };
      }
    } catch { if (current === generation) state = { status: 'unavailable', workspaceId: null, message: unavailable }; }
    if (current !== generation) return;
    onChange();
    if (state.status === 'anonymous') onRedirect('#/login');
    else if (state.status === 'unverified') onRedirect('#/verification');
  }
  async function logout() {
    if (state.status !== 'authorized') return false;
    const token = csrf;
    leave(); const current = generation;
    state.message = 'Signing out…'; onChange();
    try {
      const { status, body } = await request('/api/auth/logout', { method: 'POST', headers: { 'X-CSRF-Token': token } });
      if (current !== generation) return false;
      if (status !== 200 || body?.ok !== true) throw new Error('Unconfirmed logout');
      state = { status: 'anonymous', workspaceId: null, message: 'You are signed out.' }; onChange();
      onRedirect('#/login'); return true;
    } catch {
      if (current === generation) { state = { status: 'unavailable', workspaceId: null, message: 'Sign out could not be confirmed. Check account access and try again.' }; onChange(); }
      return false;
    }
  }
  return { snapshot, load, logout, leave };
}
