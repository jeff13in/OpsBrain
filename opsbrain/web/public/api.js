const agents = ['rag', 'monitoring', 'infra', 'code'];
const string = (value, max = 20000) => typeof value === 'string' && value.length <= max;
const sources = value => Array.isArray(value) && value.length <= 100 && value.every(item => string(item, 2000));
const count = value => Number.isInteger(value) && value >= 0;

export function validateAnswer(body, question) {
  if (!string(body?.request_id, 100) || !body.request_id || body.question !== question ||
      !['ok', 'partial', 'error'].includes(body.status) || !string(body.answer) || !sources(body.sources) ||
      !Array.isArray(body.results) || body.results.length < 1 || body.results.length > 4) throw new Error('Invalid API answer');
  const seen = new Set();
  for (const result of body.results) {
    if (!agents.includes(result?.agent) || seen.has(result.agent) || !['ok', 'error', 'timeout'].includes(result.status) || !sources(result.sources) ||
        (result.status === 'ok' ? !string(result.answer) || !result.answer.trim() : !string(result.error?.code, 100) || !string(result.error?.message, 2000)) ||
        (result.status !== 'ok' && result.sources.length)) throw new Error('Invalid agent result');
    seen.add(result.agent);
    if (result.latency_ms !== undefined && (!count(result.latency_ms) || result.latency_ms > 86400000)) throw new Error('Invalid latency');
  }
  const routing = body.routing;
  if (routing !== undefined && (!routing || !['llm', 'keyword', 'fallback'].includes(routing.method) ||
      !string(routing.reason, 2000) || !Array.isArray(routing.agents) || routing.agents.length !== seen.size ||
      new Set(routing.agents).size !== seen.size || !routing.agents.every(agent => seen.has(agent)))) throw new Error('Invalid routing');
  const successful = body.results.filter(result => result.status === 'ok');
  const expected = successful.length === body.results.length ? 'ok' : successful.length ? 'partial' : 'error';
  if (body.status !== expected || body.sources.some(source => !successful.some(result => result.sources.includes(source)))) throw new Error('Inconsistent API answer');
  return { status: body.status, answer: body.answer, sources: body.sources,
    ...(routing ? { routing: { method: routing.method, reason: routing.reason, agents: [...routing.agents] } } : {}),
    results: body.results.map(result => ({
    agent: result.agent, status: result.status, answer: result.status === 'ok' ? result.answer : null,
    sources: result.sources, error: result.status === 'ok' ? null : { code: result.error.code, message: result.error.message },
    ...(result.latency_ms !== undefined ? { latency_ms: result.latency_ms } : {}),
  })) };
}

export function createApi({ request = fetch, onChange = () => {}, sessionId = () => crypto.randomUUID() } = {}) {
  let state = { mode: 'demo', pending: false, message: '', monitoring: null };
  let controller = new AbortController();
  let generation = 0;
  let operationalGeneration = 0;
  let operationalController = new AbortController();
  let session = null;
  async function json(path, options = {}, timeout = 15000) {
    const response = await request(`/api/${path}`, { ...options, credentials: 'omit', cache: 'no-store', redirect: 'error',
      signal: AbortSignal.any([controller.signal, ...(options.signal ? [options.signal] : []), AbortSignal.timeout(timeout)]), headers: { 'Content-Type': 'application/json' } });
    if (![200, 502].includes(response.status)) throw new Error('API request unavailable');
    const text = await response.text();
    if (text.length > 1000000) throw new Error('API response too large');
    return { body: JSON.parse(text), status: response.status };
  }
  function reset(mode) {
    controller.abort(); controller = new AbortController(); generation++;
    session = null;
    state = { mode, pending: false, message: '', monitoring: null };
  }
  return {
    snapshot: () => structuredClone({ ...state, sessionActive: session !== null }),
    leaveOperational() {
      operationalController.abort(); operationalController = new AbortController(); operationalGeneration++;
      state.statusPending = false; state.seriesPending = false;
    },
    newSession() {
      controller.abort(); controller = new AbortController(); generation++;
      state.pending = false; state.monitoring = null;
      if (state.mode === 'live') session = sessionId();
    },
    disconnect(mode = 'disconnected') { reset(mode === 'demo' ? 'demo' : 'disconnected'); onChange(); },
    async refreshStatus() {
      if (state.mode !== 'live' || state.statusPending) return false;
      const current = generation, operation = operationalGeneration; state.statusPending = true; onChange();
      try {
        const { body, status } = await json('status', { signal: operationalController.signal });
        const names = ['orchestrator', 'rag', 'monitoring', 'infra', 'code'];
        if (status !== 200 || !body || typeof body.retrievedAt !== 'string' || !Number.isFinite(Date.parse(body.retrievedAt)) ||
          !Array.isArray(body.services) || body.services.length !== 5 || new Set(body.services.map(item => item.service)).size !== 5 ||
          !body.services.every(item => names.includes(item.service) && ['reachable', 'unavailable', 'unconfigured'].includes(item.reachability) && item.readiness === 'unknown')) throw new Error('Invalid status');
        if (current !== generation || operation !== operationalGeneration) return false;
        state.readiness = { retrievedAt: body.retrievedAt, stale: false,
          services: body.services.map(item => ({ service: item.service, reachability: item.reachability, readiness: item.readiness })) };
        state.statusMessage = '';
      } catch {
        if (current !== generation || operation !== operationalGeneration) return false;
        if (state.readiness) state.readiness.stale = true;
        state.statusMessage = 'Status retrieval failed. Retained results are stale.';
      }
      state.statusPending = false; onChange(); return true;
    },
    async refreshSeries(range = '15m') {
      if (state.mode !== 'live' || state.seriesPending || !['15m', '1h'].includes(range)) return false;
      const current = generation, operation = operationalGeneration; state.seriesPending = true; onChange();
      if (state.series?.range !== range) state.series = null;
      try {
        const { body, status } = await json(`monitoring/series?range=${range}`, { signal: operationalController.signal });
        const names = ['cpu', 'memory', 'latency', 'requests', 'errors', 'availability'];
        const start = Date.parse(body?.start), end = Date.parse(body?.end);
        if (status !== 200 || body?.range !== range || !Number.isFinite(start) || !Number.isFinite(end) || end - start !== (range === '15m' ? 900000 : 3600000) ||
          typeof body.retrievedAt !== 'string' || !Number.isFinite(Date.parse(body.retrievedAt)) || !body.metrics || names.some(id => !Object.hasOwn(body.metrics, id))) throw new Error('Invalid series');
        const samples = {};
        for (const id of names) {
          const row = body.metrics[id]; let previous = -Infinity;
          if (!row || !['ok', 'unavailable'].includes(row.status) || !Array.isArray(row.points) || row.points.length > 61 ||
            (row.status === 'ok') !== (row.points.length > 0)) throw new Error('Invalid metric');
          samples[id] = row.points.map(point => {
            const time = Date.parse(point.observedAt);
            if (typeof point.observedAt !== 'string' || !Number.isFinite(time) || time < start || time > end || time <= previous ||
              typeof point.value !== 'number' || !Number.isFinite(point.value) || point.value < 0 ||
              (['cpu', 'memory', 'availability'].includes(id) && point.value > 100)) throw new Error('Invalid sample');
            previous = time;
            return { minutesAgo: (end - time) / 60000, value: point.value, observedAt: point.observedAt };
          });
        }
        if (current !== generation || operation !== operationalGeneration) return false;
        state.series = { range, samples, retrievedAt: body.retrievedAt, start: body.start, end: body.end, stale: false };
        state.seriesMessage = '';
      } catch {
        if (current !== generation || operation !== operationalGeneration) return false;
        if (state.series) state.series.stale = true;
        state.seriesMessage = 'Time-series retrieval failed. Retained results are stale; no Demo fallback was used.';
      }
      state.seriesPending = false; onChange(); return true;
    },
    async connect() {
      reset('connecting'); onChange();
      const current = generation;
      try {
        const { body, status } = await json('orchestrator/health');
        if (generation !== current) return false;
        if (status !== 200 || body?.status !== 'ok' || body.agent !== 'orchestrator') throw new Error('Invalid health');
        state.mode = 'live'; session = sessionId();
        state.message = 'Orchestrator reachable. Agent availability is reported per request.';
      } catch {
        if (generation !== current) return false;
        state.mode = 'disconnected'; state.message = 'Connection failed. Check the local backend and gateway settings. No demo fallback was used.';
      }
      onChange(); return state.mode === 'live';
    },
    async ask(question) {
      if (state.mode !== 'live') throw new Error('Live API not connected');
      const current = generation;
      const { body, status } = await json('orchestrator/ask', { method: 'POST', body: JSON.stringify({ question, session_id: session }) }, 90000);
      if (current !== generation) throw new Error('Request superseded');
      const answer = validateAnswer(body, question);
      if ((status === 502) !== (answer.status === 'error')) throw new Error('Inconsistent HTTP status');
      return answer;
    },
    async refreshMonitoring() {
      if (state.mode !== 'live' || state.pending) return false;
      const current = generation;
      state.pending = true; state.monitoring = null; onChange();
      const results = await Promise.allSettled([
        json('monitoring/alerts/summary').then(({ body, status }) => {
          if (status !== 200 || !count(body?.total) || !count(body.active) || !count(body.suppressed) || body.active > body.total || body.suppressed > body.total) throw new Error('Invalid alerts');
          return { total: body.total, active: body.active, suppressed: body.suppressed };
        }),
        json('monitoring/pods/health').then(({ body, status }) => {
          if (status !== 200 || !count(body?.total_pods) || !body.status_breakdown || typeof body.status_breakdown !== 'object' || Array.isArray(body.status_breakdown) ||
            Object.entries(body.status_breakdown).length > 20 || !Object.values(body.status_breakdown).every(count) || !Array.isArray(body.pods) || body.pods.length > 10000) throw new Error('Invalid pods');
          return { total: body.total_pods, phases: Object.entries(body.status_breakdown).map(([phase, total]) => ({ phase: String(phase).slice(0, 100), total })) };
        }),
      ]);
      if (current !== generation) return false;
      state.monitoring = { observedAt: new Date().toISOString(), alerts: results[0].status === 'fulfilled' ? results[0].value : null,
        pods: results[1].status === 'fulfilled' ? results[1].value : null };
      state.pending = false; onChange(); return true;
    },
  };
}
