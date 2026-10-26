import test from 'node:test';
import assert from 'node:assert/strict';
import { AUTH_ROUTES, createAuth, validateAuth } from '../public/auth.js';
import { renderPage, routeFromHash } from '../public/ui.js';

const bootstrap = { authenticated: false, signup_enabled: true, recovery_allowed: false, csrf_token: 'a'.repeat(32) };
const input = { email: 'client@example.test', password: 'a strong password', confirmation: 'a strong password' };
const reply = (body, status = 200) => ({ status, text: async () => JSON.stringify(body) });
function fixture(responder = () => reply({ ok: true }), boot = bootstrap) {
  const calls = [];
  const auth = createAuth({ fetcher: async (url, options) => {
    calls.push({ url, options });
    return url === '/api/auth/session' ? reply(boot) : responder(url, options);
  } });
  return { auth, calls };
}

test('all account routes render one accessible heading and real password-manager fields', () => {
  for (const route of AUTH_ROUTES) {
    assert.equal(routeFromHash(`#/${route.id}`), route.id);
    const html = renderPage(route.id).html;
    assert.equal((html.match(/<h1\b/g) || []).length, 1);
    assert.match(html, /role="status"/);
    assert.match(html, /type="submit" disabled/);
    for (const [, field] of html.matchAll(/<input id="([^"]+)"/g)) assert.ok(html.includes(`for="${field}"`));
  }
  assert.match(renderPage('login').html, /autocomplete="current-password"/);
  assert.match(renderPage('login').html, /autocomplete="username"/);
  assert.match(renderPage('signup').html, /autocomplete="new-password"/);
  assert.match(renderPage('password').html, /Open a valid recovery link/);
});

test('untrusted email and errors are escaped without a password value attribute', () => {
  const html = renderPage('signup', { authState: { email: '"><script>secret</script>', errors: { email: '<script>bad</script>' } } }).html;
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /aria-invalid="true"/);
  assert.doesNotMatch(html, /<input id="auth-password"[^>]*value=/);
});

test('inline validation bounds input, confirms new passwords and supports existing short passwords', () => {
  assert.deepEqual(validateAuth('signup', input), {});
  assert.deepEqual(validateAuth('login', { ...input, password: 'short' }), {});
  assert.ok(validateAuth('signup', { ...input, password: 'short' }).password);
  assert.ok(validateAuth('password', { ...input, confirmation: 'different' }).confirmation);
  assert.ok(validateAuth('recovery', { email: 'invalid' }).email);
  assert.ok(validateAuth('login', { ...input, password: 'x'.repeat(129) }).password);
  assert.ok(validateAuth('__proto__', input).form);
});

test('missing or malformed bootstrap keeps forms disabled and sends no password', async () => {
  for (const boot of [null, {}, { ...bootstrap, csrf_token: 'invalid' }, { ...bootstrap, signup_enabled: 'true' }]) {
    const { auth, calls } = fixture(undefined, boot);
    await auth.load();
    assert.equal(auth.snapshot().ready, false);
    await auth.submit('login', input);
    assert.equal(calls.length, 1);
  }
  const auth = createAuth({ fetcher: async () => reply({}, 503) });
  await auth.load();
  assert.equal(auth.snapshot().ready, false);
});

test('signup and password updates require server-owned eligibility/recovery flags', async () => {
  const { auth, calls } = fixture(undefined, { ...bootstrap, signup_enabled: false });
  await auth.load();
  await auth.submit('signup', input);
  await auth.submit('password', input);
  assert.equal(calls.length, 1);
  assert.match(renderPage('signup', { authState: auth.snapshot() }).html, /type="submit" disabled/);
});

test('invalid input stays local and never creates a pending credential request', async () => {
  const { auth, calls } = fixture();
  await auth.load();
  await auth.submit('signup', { ...input, confirmation: 'mismatch' });
  assert.equal(calls.length, 1);
  assert.ok(auth.snapshot().errors.confirmation);
  assert.equal(auth.snapshot().pending, false);
});

test('login posts only to same origin with CSRF and never snapshots the password or token', async () => {
  const { auth, calls } = fixture();
  await auth.load();
  await auth.submit('login', input);
  const { url, options } = calls[1];
  assert.equal(url, '/api/auth/login');
  assert.equal(options.credentials, 'same-origin');
  assert.equal(options.redirect, 'error');
  assert.equal(options.cache, 'no-store');
  assert.equal(options.headers['X-CSRF-Token'], bootstrap.csrf_token);
  assert.deepEqual(JSON.parse(options.body), { email: input.email, password: input.password });
  assert.match(auth.snapshot().message, /You are signed in/);
  assert.ok(!JSON.stringify(auth.snapshot()).includes(input.password));
  assert.ok(!JSON.stringify(auth.snapshot()).includes(bootstrap.csrf_token));
  assert.equal(auth.snapshot().ready, false, 'mutation rotates bootstrap before further submission');
});

test('signup, verification resend and recovery use generic account-safe acknowledgements', async () => {
  for (const [route, path, message] of [
    ['signup', 'signup', /If your address is eligible/],
    ['verification', 'resend', /If a verification message can be sent/],
    ['recovery', 'recovery', /If a reset is available/],
  ]) {
    const { auth, calls } = fixture();
    await auth.load(); await auth.submit(route, input);
    assert.equal(calls[1].url, `/api/auth/${path}`);
    assert.match(auth.snapshot().message, message);
    assert.equal(Object.hasOwn(JSON.parse(calls[1].options.body), 'password'), route === 'signup');
  }
});

test('password recovery permission allows only password payload and then clears recovery', async () => {
  const { auth, calls } = fixture(undefined, { ...bootstrap, recovery_allowed: true });
  await auth.load(); await auth.submit('password', input);
  assert.deepEqual(JSON.parse(calls[1].options.body), { password: input.password });
  assert.equal(auth.snapshot().recoveryAllowed, false);
  assert.match(auth.snapshot().message, /Log in again/);
});

test('invalid credentials, throttling, expired links and outages show safe messages', async () => {
  for (const [status, message] of [[401, /email or password could not be verified/], [429, /Too many attempts/], [503, /temporarily unavailable/], [409, /temporarily unavailable/]]) {
    const { auth } = fixture(() => reply({ error: 'SECRET: existing account client@example.test' }, status));
    await auth.load(); await auth.submit('login', input);
    assert.match(auth.snapshot().message, message);
    assert.doesNotMatch(auth.snapshot().message, /SECRET|existing account/);
  }
  const { auth } = fixture(() => reply({}, 403));
  await auth.load(); await auth.submit('verification', input);
  assert.match(auth.snapshot().message, /Request a fresh link/);
  assert.equal(auth.snapshot().ready, false);
});

test('malformed, oversized and non-success JSON never announce successful authentication', async () => {
  for (const response of [reply({}), { status: 200, text: async () => 'not JSON' }, { status: 200, text: async () => 'x'.repeat(8193) }]) {
    const { auth } = fixture(() => response);
    await auth.load(); await auth.submit('login', input);
    assert.match(auth.snapshot().message, /temporarily unavailable/);
    assert.equal(auth.snapshot().pending, false);
  }
});

test('navigation cancellation prevents late success from resurrecting account state', async () => {
  let finish;
  const { auth, calls } = fixture(() => new Promise(resolve => { finish = resolve; }));
  await auth.load();
  const pending = auth.submit('login', input);
  assert.equal(auth.snapshot().pending, true);
  await auth.submit('login', input);
  assert.equal(calls.length, 2, 'duplicate submission suppressed');
  auth.leave();
  assert.equal(calls[1].options.signal.aborted, true);
  finish(reply({ ok: true })); await pending;
  assert.equal(auth.snapshot().ready, false);
  assert.equal(auth.snapshot().email, '');
  assert.doesNotMatch(auth.snapshot().message, /signed in/);
});

test('request deadline ends pending state without leaking transport errors', async () => {
  const auth = createAuth({ timeoutMs: 5, fetcher: (url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(new Error('SECRET connection details')), { once: true });
  }) });
  await auth.load();
  assert.equal(auth.snapshot().pending, false);
  assert.match(auth.snapshot().message, /temporarily unavailable/);
});

test('Google sign-in link appears only when the server enables it, on login and signup', async () => {
  const off = fixture();
  await off.auth.load();
  assert.doesNotMatch(renderPage('login', { authState: off.auth.snapshot() }).html, /auth-google/);
  const on = fixture(undefined, { ...bootstrap, google_enabled: true });
  await on.auth.load();
  for (const id of ['login', 'signup']) {
    const html = renderPage(id, { authState: on.auth.snapshot() }).html;
    assert.match(html, /<a id="auth-google" class="button secondary google-button" href="\/auth\/google\/start">/);
    assert.match(html, /aria-hidden="true"[^>]*>.*Continue with Google<\/a>/s);
  }
  for (const id of ['recovery', 'verification', 'password']) {
    assert.doesNotMatch(renderPage(id, { authState: on.auth.snapshot() }).html, /auth-google/);
  }
  const loose = fixture(undefined, { ...bootstrap, google_enabled: 'true' });
  await loose.auth.load();
  assert.equal(loose.auth.snapshot().googleEnabled, false);
});

test('a failed Google return shows a generic status message', async () => {
  const { auth } = fixture(undefined, { ...bootstrap, google_enabled: true });
  await auth.load();
  const html = renderPage('login', { authState: { ...auth.snapshot(), googleFailed: true } }).html;
  assert.match(html, /Google sign-in did not complete/);
});
