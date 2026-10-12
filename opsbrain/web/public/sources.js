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

export function openSourceTarget(target) {
  if (!target) return;
  const detail = target.querySelector('details');
  if (detail) detail.open = true;
  target.scrollIntoView({ block: 'nearest' });
  target.focus({ preventScroll: true });
}
