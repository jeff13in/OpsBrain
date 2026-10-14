// Fixed local service targets and server-owned metric queries. Not a production
// authentication boundary; the development gateway remains loopback-only.
export const presets = Object.freeze({
  cpu: '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))',
  memory: '100 * (1 - sum(node_memory_MemAvailable_bytes) / sum(node_memory_MemTotal_bytes))',
  latency: '1000 * histogram_quantile(0.95, sum by (le) (rate(opsbrain_http_request_duration_seconds_bucket[5m])))',
  requests: 'sum(increase(opsbrain_http_requests_total[5m]))',
  errors: 'sum(increase(opsbrain_http_requests_total{status_code=~"5.."}[5m]))',
  availability: '100 * avg(up{job=~"opsbrain-.*"})',
});

export async function boundedJson(request, url, options, signal) {
  const response = await request(url, { ...options, signal, redirect: 'error', headers: { 'Content-Type': 'application/json' } });
  if (response.status !== 200) throw new Error('Unavailable');
  let length = 0; const parts = [];
  for await (const chunk of response.body) {
    length += chunk.length;
    if (length > 200000) throw new Error('Oversized');
    parts.push(Buffer.from(chunk));
  }
  return JSON.parse(Buffer.concat(parts).toString('utf8'));
}

export function normalizeSeries(body, start, end) {
  if (body?.result_type !== 'matrix' || !Array.isArray(body.result) || body.result.length > 1) throw new Error('Invalid series');
  if (!body.result.length) return [];
  const values = body.result[0]?.values;
  if (!Array.isArray(values) || values.length > 61) throw new Error('Invalid samples');
  let previous = -Infinity;
  return values.map(pair => {
    if (!Array.isArray(pair) || pair.length !== 2 || typeof pair[0] !== 'number' ||
        (typeof pair[1] !== 'string' && typeof pair[1] !== 'number') || String(pair[1]).trim() === '') throw new Error('Invalid point');
    const [time, raw] = pair; const value = Number(raw);
    if (!Number.isFinite(time) || time < start || time > end || time <= previous || !Number.isFinite(value) || value < 0) throw new Error('Invalid point');
    previous = time;
    return { minutesAgo: (end - time) / 60, value, observedAt: new Date(time * 1000).toISOString() };
  });
}

export async function operational(path, url, origins, request, signal, now = Date.now) {
  if (path === '/api/status') {
    if (url.search) throw new Error('Invalid options');
    const services = await Promise.all(['orchestrator', 'rag', 'monitoring', 'infra', 'code'].map(async service => {
      if (!origins[service]) return { service, reachability: 'unconfigured', readiness: 'unknown' };
      try {
        const body = await boundedJson(request, origins[service] + '/health', { method: 'GET' }, signal);
        if (body?.status !== 'ok') throw new Error('Invalid health');
        // Existing /health responses do not verify operational dependencies.
        return { service, reachability: 'reachable', readiness: 'unknown' };
      } catch { return { service, reachability: 'unavailable', readiness: 'unknown' }; }
    }));
    return { retrievedAt: new Date(now()).toISOString(), services };
  }
  const range = url.searchParams.get('range');
  if (!['15m', '1h'].includes(range) || [...url.searchParams.keys()].some(key => key !== 'range') || url.searchParams.getAll('range').length !== 1) throw new Error('Invalid range');
  const end = Math.floor(now() / 1000), start = end - (range === '15m' ? 900 : 3600);
  const results = await Promise.all(Object.entries(presets).map(async ([id, query]) => {
    try {
      if (!origins.monitoring) throw new Error('Unconfigured');
      const body = await boundedJson(request, origins.monitoring + '/metrics/query', { method: 'POST',
        body: JSON.stringify({ query, start: new Date(start * 1000).toISOString(), end: new Date(end * 1000).toISOString(), step: '60s' }) }, signal);
      const points = normalizeSeries(body, start, end);
      if (['cpu', 'memory', 'availability'].includes(id) && points.some(point => point.value > 100)) throw new Error('Invalid percent');
      return [id, { status: points.length ? 'ok' : 'unavailable', points }];
    } catch { return [id, { status: 'unavailable', points: [] }]; }
  }));
  return { retrievedAt: new Date(now()).toISOString(), range, start: new Date(start * 1000).toISOString(), end: new Date(end * 1000).toISOString(), metrics: Object.fromEntries(results) };
}
