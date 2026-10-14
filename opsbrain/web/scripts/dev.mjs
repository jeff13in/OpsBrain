import { createPreviewServer } from './server.mjs';
import { createGateway } from './gateway.mjs';

const port = Number(process.env.OPSBRAIN_WEB_PORT || 4173);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('OPSBRAIN_WEB_PORT must be a valid port.');
const gateway = process.env.OPSBRAIN_WEB_API === '1' ? createGateway({
  orchestrator: process.env.OPSBRAIN_WEB_ORCHESTRATOR || 'http://127.0.0.1:8000',
  monitoring: process.env.OPSBRAIN_WEB_MONITORING || 'http://127.0.0.1:8002',
  rag: process.env.OPSBRAIN_WEB_RAG || 'http://127.0.0.1:8001',
  infra: process.env.OPSBRAIN_WEB_INFRA || 'http://127.0.0.1:8003',
  code: process.env.OPSBRAIN_WEB_CODE || 'http://127.0.0.1:8004',
}) : undefined;
const server = createPreviewServer(undefined, { gateway });
server.on('error', error => { console.error(`Preview failed: ${error.code || 'server error'}`); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`OpsBrain preview: http://127.0.0.1:${port}/ (${gateway ? 'local API gateway enabled; use Connect live to check reachability' : 'demo only; local API gateway disabled'})`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close());
