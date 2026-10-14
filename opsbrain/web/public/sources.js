// Explicit synthetic passages; source labels never become filesystem paths or URLs.
const demoPassages = Object.freeze({
  'Example runbook: service latency': 'Synthetic runbook passage: Check CPU saturation and pod readiness before changing capacity. Inspect the unready pod and compare its timeline with deployment changes. Correlation alone does not establish a cause.',
});

export function sourcePassage(source, mode) {
  if (mode === 'demo' && typeof source === 'string' && Object.hasOwn(demoPassages, source)) {
    return { available: true, provenance: 'Synthetic example · fixture revision 1', passage: demoPassages[source] };
  }
  return { available: false, provenance: mode === 'live' ? 'API source label only' : 'Synthetic source label only',
    passage: mode === 'live' ? 'The API supplied a source label without a retrieved passage. Passage access is unavailable until the authorized source service is connected.' : 'No example passage is provided for this source.' };
}

const sourceOpeners = new WeakMap();
export function openSourceTarget(target, trigger) {
  if (!target) return;
  const detail = target.querySelector('details');
  if (detail) {
    if (trigger) sourceOpeners.set(detail, trigger);
    if (!detail.dataset?.passageEscape && detail.addEventListener) {
      detail.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
          event.preventDefault(); detail.open = false; sourceOpeners.get(detail)?.focus();
        }
      });
      if (detail.dataset) detail.dataset.passageEscape = 'true';
    }
    detail.open = true;
  }
  target.scrollIntoView({ block: 'nearest' });
  target.focus({ preventScroll: true });
}

const sourceId = /^src_[a-f0-9]{64}$/;
export function validatePassage(value, expectedSource) {
  const bounded = (v, n) => typeof v === 'string' && v.length > 0 && v.length <= n;
  if (!value || !sourceId.test(expectedSource) || value.source_id !== expectedSource ||
      typeof value.available !== 'boolean' || value.provenance !== 'retrieved') throw new Error('Invalid passage');
  const revision = value.revision ?? null, observed = value.observed_at ?? null, passage = value.passage ?? null;
  if (!value.available) {
    if (passage !== null || revision !== null || observed !== null) throw new Error('Invalid unavailable passage');
  } else {
    if (!bounded(passage, 8000) || !passage.trim() || (revision !== null && !bounded(revision, 200)) ||
        (observed !== null && (typeof observed !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(observed) ||
          !Number.isFinite(Date.parse(observed)) || new Date(observed).toISOString() !== observed.replace('Z', '.000Z')))) throw new Error('Invalid passage');
  }
  return { source_id: expectedSource, available: value.available, provenance: 'retrieved', passage, revision, observed_at: observed };
}
