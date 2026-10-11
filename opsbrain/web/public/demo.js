// Synthetic, deterministic examples. Never used as a fallback for live requests.
const freeze = value => {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
};

export const DEMO_STATES = freeze([
  { id: 'populated', label: 'Populated' },
  { id: 'partial', label: 'Partial availability' },
  { id: 'loading', label: 'Loading' },
  { id: 'empty', label: 'Empty' },
  { id: 'error', label: 'Error' },
  { id: 'disconnected', label: 'Disconnected' },
]);

export const DEMO_FIXTURE = freeze({
  agents: {
    RAG: { summary: '2 example runbooks available', outcome: 'Sample context ready' },
    Monitoring: { summary: '1 example warning alert', outcome: 'Sample context ready' },
    Infra: { summary: '3 example pods inspected', outcome: 'Sample context ready' },
    Code: { summary: '1 example change to review', outcome: 'Sample context ready' },
  },
  signals: [
    { label: 'CPU utilization', value: '68%', detail: 'Synthetic service average' },
    { label: 'Ready pods', value: '2 / 3', detail: 'Synthetic cluster snapshot' },
    { label: 'Warning alerts', value: '1', detail: 'Synthetic alert count' },
  ],
  activity: [
    { agent: 'Monitoring', title: 'CPU warning in example service', detail: 'Demo alert · no real incident' },
    { agent: 'Infra', title: 'One example pod is not ready', detail: 'Demo snapshot · no cluster queried' },
    { agent: 'Code', title: 'Example deployment changed connection pooling', detail: 'Demo change · no repository queried' },
  ],
});

export function demoState(value) {
  return DEMO_STATES.some(state => state.id === value) ? value : 'disconnected';
}

export function demoStateFromHash(hash) {
  return demoState(new URLSearchParams(String(hash).split('?')[1] || '').get('state'));
}
