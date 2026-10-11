import { createPreviewServer } from './server.mjs';
import { createGateway } from './gateway.mjs';

const port = Number(process.env.OPSBRAIN_WEB_PORT || 4173);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('OPSBRAIN_WEB_PORT must be a valid port.');
const gateway = process.env.OPSBRAIN_WEB_API === '1' ? createGateway({
  orchestrator: process.env.OPSBRAIN_WEB_ORCHESTRATOR || 'http://127.0.0.1:8000',
  monitoring: process.env.OPSBRAIN_WEB_MONITORING || 'http://127.0.0.1:8002',
}) : undefined;
const server = createPreviewServer(undefined, { gateway });
server.on('error', error => { console.error(`Preview failed: ${error.code || 'server error'}`); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`OpsBrain local foundation: http://127.0.0.1:${port}/ (no backend connected)`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close());
