// Synthetic chart samples only. No monitoring service is contacted.
export const MONITORING_SCENARIOS = Object.freeze([
  { id: 'populated', label: 'Populated' },
  { id: 'partial', label: 'Latency unavailable' },
  { id: 'empty', label: 'Empty' },
  { id: 'error', label: 'Error' },
  { id: 'disconnected', label: 'Disconnected' },
]);
export const MONITORING_RANGES = Object.freeze([
  { id: '15m', label: 'Last 15 minutes', minutes: 15 },
  { id: '1h', label: 'Last hour', minutes: 60 },
]);
export const METRICS = Object.freeze([
  { id: 'cpu', title: 'CPU utilization', unit: '%', maximum: 100 },
  { id: 'memory', title: 'Memory utilization', unit: '%', maximum: 100 },
  { id: 'latency', title: 'Response latency (p95)', unit: 'ms', maximum: 500 },
  { id: 'requests', title: 'Requests in preceding 5 minutes', unit: 'requests', maximum: 200 },
  { id: 'errors', title: 'Server errors in preceding 5 minutes', unit: 'errors', maximum: 20 },
  { id: 'availability', title: 'Service scrape availability', unit: '%', maximum: 100 },
]);

export function sampleSnapshot(scenario, range, revision = 0) {
  if (!MONITORING_SCENARIOS.some(item => item.id === scenario) || !MONITORING_RANGES.some(item => item.id === range)) throw new Error('Unknown monitoring preview option');
  const values = {
    cpu: [42, 46, 44, 49, 53, 57, 51, 58, 61, 64, 66, 68],
    memory: [51, 51, 52, 54, 53, 56, 57, 56, 58, 60, 61, 62],
    latency: [120, 125, 118, 140, 145, 152, 170, 190, 210, 205, 240, 260],
    requests: [80, 85, 90, 95, 100, 90, 105, 100, 115, 120, 125, 130],
    errors: [0, 1, 0, 0, 2, 1, 1, 0, 2, 3, 2, 1],
    availability: [100, 100, 100, 100, 100, 100, 80, 80, 100, 100, 100, 100],
  };
  const unavailable = ['empty', 'error', 'disconnected'].includes(scenario);
  return Object.fromEntries(METRICS.map(metric => [metric.id,
    unavailable || (scenario === 'partial' && metric.id === 'latency') ? [] : values[metric.id]
      .map((value, index) => ({ minutesAgo: (11 - index) * 5, value: value + (revision % 2 ? (metric.id === 'availability' ? -2 : metric.id === 'latency' ? 10 : 2) : 0) }))
      .filter(point => range === '1h' || point.minutesAgo <= 15),
  ]));
}

export async function loadMonitoring(scenario, range, revision) {
  await new Promise(resolve => setTimeout(resolve, 300));
  return sampleSnapshot(scenario, range, revision);
}

export function createMonitoring({ load = loadMonitoring, now = () => new Date().toISOString(), onChange = () => {}, schedule = setInterval, unschedule = clearInterval } = {}) {
  let state = { scenario: 'disconnected', range: '15m', pending: false, samples: null, refreshedAt: null, revision: 0, auto: false };
  let active = false;
  let generation = 0;
  let timer = null;
  function stopAuto() {
    if (timer !== null) unschedule(timer);
    timer = null;
    state.auto = false;
  }
  const controller = {
    snapshot: () => structuredClone(state),
    setActive(value) {
      active = Boolean(value);
      if (!active) {
        stopAuto();
        generation++;
        if (state.pending) { state.samples = null; state.refreshedAt = null; state.scenario = 'disconnected'; }
        state.pending = false;
      }
    },
    setAuto(enabled) {
      stopAuto();
      if (enabled && active && state.scenario !== 'disconnected') {
        state.auto = true;
        timer = schedule(() => { void controller.refresh(); }, 30000);
      }
      onChange();
    },
    async select(scenario, range) {
      if (!MONITORING_SCENARIOS.some(item => item.id === scenario) || !MONITORING_RANGES.some(item => item.id === range)) return false;
      generation++;
      state.pending = false;
      state.scenario = scenario;
      state.range = range;
      if (scenario === 'disconnected') stopAuto();
      return controller.refresh();
    },
    async refresh() {
      if (!active || state.pending) return false;
      const requestGeneration = ++generation;
      state.pending = true;
      state.samples = null;
      state.refreshedAt = null;
      onChange();
      try {
        const samples = await load(state.scenario, state.range, state.revision);
        if (generation !== requestGeneration) return false;
        state.samples = samples;
        state.refreshedAt = now();
        state.revision++;
      } catch {
        if (generation !== requestGeneration) return false;
        state.scenario = 'error';
        state.samples = null;
        stopAuto();
      }
      state.pending = false;
      onChange();
      return true;
    },
  };
  return controller;
}
