// Local development gateway. Only selected read/query endpoints are forwarded.
import { operational } from './operational.mjs';
const routes = {
  '/api/orchestrator/health': { service: 'orchestrator', path: '/health', method: 'GET' },
  '/api/orchestrator/ask': { service: 'orchestrator', path: '/ask', method: 'POST' },
  '/api/monitoring/alerts/summary': { service: 'monitoring', path: '/alerts/summary', method: 'GET' },
  '/api/monitoring/pods/health': { service: 'monitoring', path: '/pods/health', method: 'GET' },
};
function base(value) {
  if (!value) return null;
  const url = new URL(value);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error('Gateway upstream must be a plain http://127.0.0.1:port origin');
  return url.origin;
}
export function createGateway({ orchestrator, monitoring, rag, infra, code, request = fetch } = {}) {
  const origins = { orchestrator: base(orchestrator), monitoring: base(monitoring), rag: base(rag), infra: base(infra), code: base(code) };
  return async (incoming, outgoing, url) => {
    const respond = (status, message) => { outgoing.writeHead(status, { 'Content-Type': 'application/json' }); outgoing.end(JSON.stringify({ error: message })); };
    const aggregate = ['/api/status', '/api/monitoring/series'].includes(url.pathname);
    const route = aggregate ? { method: 'GET' } : routes[url.pathname];
    if (!route || (!aggregate && url.search)) { respond(404, 'Unknown API route'); return; }
    if (incoming.method !== route.method) { respond(405, 'Method not allowed'); return; }
    if (!aggregate && !origins[route.service]) { respond(503, 'Local gateway service is not configured'); return; }
    const expectedHost = `127.0.0.1:${incoming.socket.localPort}`;
    if (incoming.headers.host !== expectedHost ||
        (incoming.headers.origin && incoming.headers.origin !== `http://${expectedHost}`) ||
        (incoming.headers['sec-fetch-site'] && !['same-origin', 'none'].includes(incoming.headers['sec-fetch-site']))) { respond(403, 'Same-origin localhost requests only'); return; }
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), route.method === 'POST' ? 90000 : 15000);
    outgoing.on('close', () => abort.abort());
    try {
      if (aggregate) {
        if ((url.pathname === '/api/status' && url.search) || (url.pathname === '/api/monitoring/series' &&
            (!['15m', '1h'].includes(url.searchParams.get('range')) || [...url.searchParams.keys()].some(key => key !== 'range') || url.searchParams.getAll('range').length !== 1))) {
          respond(400, 'Invalid options'); return;
        }
        const result = await operational(url.pathname, url, origins, request, abort.signal);
        outgoing.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); outgoing.end(JSON.stringify(result)); return;
      }
      let body;
      if (route.method === 'POST') {
        if (!incoming.headers['content-type']?.startsWith('application/json')) { respond(415, 'JSON required'); return; }
        const parts = []; let size = 0;
        for await (const chunk of incoming) {
          size += chunk.length;
          if (size > 16000) { respond(413, 'Request too large'); return; }
          parts.push(chunk);
        }
        let parsed;
        try { parsed = JSON.parse(Buffer.concat(parts).toString('utf8')); } catch { respond(400, 'Invalid JSON'); return; }
        if (typeof parsed?.question !== 'string' || parsed.question.trim().length < 5 || parsed.question.length > 2000 ||
            (parsed.session_id !== undefined && (typeof parsed.session_id !== 'string' || !/^[a-zA-Z0-9-]{1,100}$/.test(parsed.session_id))) ||
            Object.keys(parsed).some(key => !['question', 'session_id'].includes(key))) { respond(400, 'Invalid question request'); return; }
        body = JSON.stringify(parsed);
      }
      const response = await request(origins[route.service] + route.path, { method: route.method, body,
        headers: { 'Content-Type': 'application/json' }, signal: abort.signal, redirect: 'error' });
      if (![200, 502].includes(response.status)) { respond(response.status === 401 || response.status === 403 ? response.status : 503, 'Backend request unavailable'); return; }
      const chunks = []; let bytes = 0;
      for await (const chunk of response.body) {
        bytes += chunk.length;
        if (bytes > 1000000) throw new Error('Response too large');
        chunks.push(Buffer.from(chunk));
      }
      const text = Buffer.concat(chunks).toString('utf8');
      JSON.parse(text);
      outgoing.writeHead(response.status, { 'Content-Type': 'application/json' }); outgoing.end(text);
    } catch { if (!outgoing.writableEnded) respond(503, 'Backend request unavailable'); }
    finally { clearTimeout(timer); }
  };
}
