import { fileURLToPath } from 'node:url';

export const webRoot = fileURLToPath(new URL('../', import.meta.url));
export const publicRoot = fileURLToPath(new URL('../public/', import.meta.url));
export const distRoot = fileURLToPath(new URL('../dist/', import.meta.url));
// Explicit assets only: never copy the backend checkout, environment or credentials.
export const assets = Object.freeze(['index.html', 'styles.css', 'app.js', 'ui.js', 'mark.svg']);
