import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { assets, publicRoot } from './files.mjs';

const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml' };

export function createPreviewServer(root = publicRoot) {
  return createServer(async (request, response) => {
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Referrer-Policy', 'no-referrer');
    response.setHeader('Cache-Control', 'no-store');
    response.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'");
    if (!['GET', 'HEAD'].includes(request.method)) {
      response.writeHead(405, { Allow: 'GET, HEAD' });
      response.end('Read-only preview');
      return;
    }
    let pathname;
    try { pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname); }
    catch { response.writeHead(400); response.end('Invalid path'); return; }
    const name = pathname === '/' ? 'index.html' : pathname.slice(1);
    if (!assets.includes(name)) { response.writeHead(404); response.end('Not found'); return; }
    try {
      const content = await readFile(join(root, name));
      response.writeHead(200, { 'Content-Type': types[name.slice(name.lastIndexOf('.'))] });
      response.end(request.method === 'HEAD' ? undefined : content);
    } catch { response.writeHead(500); response.end('Preview asset unavailable'); }
  });
}
