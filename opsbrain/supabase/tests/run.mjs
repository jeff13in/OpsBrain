// Isolate each WASM PostgreSQL suite and bound stalled worker startup/teardown.
import { readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
for (const name of readdirSync(new URL('./', import.meta.url)).filter(name => name.endsWith('.test.mjs')).sort()) {
  const result = spawnSync(process.execPath, ['tests/' + name], {
    cwd: root, stdio: 'inherit', timeout: 60000, killSignal: 'SIGKILL',
  });
  if (result.error || result.status !== 0) {
    console.error(`Database suite ${name} failed${result.error?.code === 'ETIMEDOUT' ? ': exceeded 60-second worker limit' : ''}`);
    process.exit(result.status || 1);
  }
}
