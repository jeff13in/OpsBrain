import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, readFile, rename, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { assets } from '../scripts/files.mjs';
import { build } from '../scripts/build.mjs';
import { createPreviewServer } from '../scripts/server.mjs';

test('build copies only allowlisted static assets, with source modules intact', async () => {
  const output = await mkdtemp(join(tmpdir(), 'opsbrain-web-test-'));
  try {
    assert.deepEqual(await build(output), assets);
    assert.deepEqual((await readdir(output)).sort(), [...assets].sort());
    assert.match(await readFile(join(output, 'app.js'), 'utf8'), /from '.\/ui.js'/);
    await build(output); // A repeat build is safe and deterministic.
    await rename(join(output, 'mark.svg'), join(output, 'unrelated.svg'));
    await assert.rejects(() => build(output), /Unexpected output files/);
    assert.ok((await readdir(output)).includes('unrelated.svg'));
  } finally { await rm(output, { recursive: true }); } // Only this test's freshly created temp directory.
});

test('loopback preview serves modules and refuses backend/secrets/mutations', async () => {
  const server = createPreviewServer();
  server.listen(0, '127.0.0.1');
  try {
    await once(server, 'listening');
    const origin = `http://127.0.0.1:${server.address().port}`;
    for (const path of ['/', '/index.html', '/styles.css', '/app.js', '/ui.js', '/mark.svg']) {
      const response = await fetch(origin + path);
      assert.equal(response.status, 200, path);
      assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
      assert.match(response.headers.get('content-security-policy'), /connect-src 'none'/);
      await response.text();
    }
    for (const path of ['/.env', '/package.json', '/agents/rag/main.py', '/%2e%2e%2f.env', '/not-a-route', '/%zz']) {
      const response = await fetch(origin + path);
      assert.ok([400, 404].includes(response.status), path);
      await response.text();
    }
    const denied = await fetch(origin + '/ask', { method: 'POST', body: '{}' });
    assert.equal(denied.status, 405); await denied.text();
    const head = await fetch(origin + '/', { method: 'HEAD' });
    assert.equal(head.status, 200); assert.equal(await head.text(), '');
  } finally { await new Promise(resolve => server.close(resolve)); }
});
