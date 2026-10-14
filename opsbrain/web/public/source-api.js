import { validatePassage } from './sources.js';
const sourceId = /^src_[a-f0-9]{64}$/;
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
// Prepared for the future account live view. It is not enabled by login alone.
// A caller must supply the verified live capability and reset on every identity,
// navigation or session change; no token or response is persisted.
export function createPassageClient({ fetcher = (...args) => globalThis.fetch(...args), timeoutMs = 5000 } = {}) {
  let scope = null, generation = 0, controller = null;
  let state = { status: 'unavailable', value: null };
  function leave() { generation++; controller?.abort(); controller = null; scope = null; state = { status: 'unavailable', value: null }; }
  return {
    snapshot: () => structuredClone(state),
    leave,
    authorize(identity) {
      leave();
      if (identity?.authorized === true && identity?.liveSourcesEnabled === true &&
          typeof identity.userId === 'string' && uuid.test(identity.userId) &&
          typeof identity.workspaceId === 'string' && uuid.test(identity.workspaceId)) {
        scope = { userId: identity.userId, workspaceId: identity.workspaceId };
      }
    },
    async load(investigationId, id) {
      controller?.abort(); generation++; const current = generation;
      state = { status: 'unavailable', value: null };
      if (!scope || typeof investigationId !== 'string' || !uuid.test(investigationId) ||
          typeof id !== 'string' || !sourceId.test(id)) return false;
      const active = new AbortController(); controller = active;
      const timer = setTimeout(() => active.abort(), timeoutMs);
      const cancelled = new Promise((_, reject) => active.signal.addEventListener('abort', () => reject(new Error('Passage unavailable')), { once: true }));
      state = { status: 'loading', value: null };
      try {
        const response = await Promise.race([fetcher(`/api/workspaces/${scope.workspaceId}/investigations/${investigationId}/sources/${id}`, {
          credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: active.signal, headers: { Accept: 'application/json' },
        }), cancelled]);
        if (response.status !== 200) throw new Error('Passage unavailable');
        const text = await Promise.race([response.text(), cancelled]);
        if (text.length > 65536) throw new Error('Oversized passage');
        const value = validatePassage(JSON.parse(text), id);
        if (current !== generation) return false;
        if (active.signal.aborted) throw new Error('Passage unavailable');
        state = { status: value.available ? 'ready' : 'unavailable', value };
        return value.available;
      } catch {
        if (current === generation) state = { status: 'unavailable', value: null };
        return false;
      } finally { clearTimeout(timer); if (current === generation) controller = null; }
    },
  };
}
