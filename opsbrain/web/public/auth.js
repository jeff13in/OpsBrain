// Same-origin auth only. Passwords/tokens never enter snapshots or browser storage.
export const AUTH_ROUTES = Object.freeze([
  { id: 'login', title: 'Log in', hidden: true },
  { id: 'signup', title: 'Sign up', hidden: true },
  { id: 'verification', title: 'Check your email', hidden: true },
  { id: 'recovery', title: 'Reset your password', hidden: true },
  { id: 'password', title: 'Choose a new password', hidden: true },
]);

const actions = Object.freeze({ login: 'login', signup: 'signup', verification: 'resend', recovery: 'recovery', password: 'password' });
const emailMessage = 'Enter a valid email address.';
const unavailable = 'Account access is temporarily unavailable. Please try again later.';

export function validateAuth(action, input = {}) {
  if (!Object.hasOwn(actions, action)) return { form: 'Choose an account action.' };
  const errors = {};
  const email = String(input.email || '').trim();
  const password = String(input.password || '');
  if (action !== 'password' && (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))) errors.email = emailMessage;
  if (['login', 'signup', 'password'].includes(action)) {
    if (!password.length || password.length > 128) errors.password = 'Enter a password of at most 128 characters.';
    else if (action !== 'login' && password.length < 12) errors.password = 'Use at least 12 characters.';
    if (action !== 'login' && password !== input.confirmation) errors.confirmation = 'The passwords must match.';
  }
  return errors;
}

export function createAuth({ fetcher = (...args) => globalThis.fetch(...args), onChange = () => {}, onLogin = () => {}, timeoutMs = 10000 } = {}) {
  let state = { ready: false, pending: false, signupEnabled: false, recoveryAllowed: false, message: unavailable, email: '', errors: {} };
  let csrf = '', generation = 0, controller;
  const emit = () => onChange();
  const snapshot = () => ({ ...state, errors: { ...state.errors } });
  function leave() {
    generation++;
    controller?.abort();
    csrf = '';
    state = { ready: false, pending: false, signupEnabled: false, recoveryAllowed: false, message: unavailable, email: '', errors: {} };
  }
  async function request(path, payload) {
    const requestController = new AbortController();
    controller = requestController;
    const timer = setTimeout(() => requestController.abort(), timeoutMs);
    try {
      const response = await fetcher(path, {
        method: payload ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal: requestController.signal,
        headers: payload ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } : { Accept: 'application/json' },
        ...(payload ? { body: JSON.stringify(payload) } : {}),
      });
      // Status-only failure messages avoid leaking arbitrary provider bodies.
      if (response.status !== 200) return { status: response.status };
      const text = await response.text();
      if (text.length > 8192) throw new Error('Oversized auth response');
      return { status: response.status, body: JSON.parse(text) };
    } finally { clearTimeout(timer); }
  }
  async function load() {
    if (state.pending) return;
    const current = ++generation;
    state = { ...state, ready: false, pending: true, errors: {}, message: 'Checking account access…' }; emit();
    try {
      const { status, body } = await request('/api/auth/session');
      if (current !== generation) return;
      if (status !== 200 || !body || typeof body.authenticated !== 'boolean' || typeof body.signup_enabled !== 'boolean'
        || typeof body.recovery_allowed !== 'boolean' || typeof body.csrf_token !== 'string'
        || !/^[A-Za-z0-9_-]{32,256}$/.test(body.csrf_token)) throw new Error('Invalid bootstrap');
      csrf = body.csrf_token;
      state = { ...state, ready: true, signupEnabled: body.signup_enabled, recoveryAllowed: body.recovery_allowed,
        message: body.authenticated ? 'You are signed in.' : '' };
    } catch { if (current === generation) { csrf = ''; state = { ...state, ready: false, message: unavailable }; } }
    finally { if (current === generation) { state.pending = false; emit(); } }
  }
  async function submit(action, input = {}) {
    if (state.pending) return;
    if (!state.ready || (action === 'signup' && !state.signupEnabled) || (action === 'password' && !state.recoveryAllowed)) {
      state = { ...state, message: action === 'signup' && state.ready ? 'Sign up is currently limited to approved beta clients.' : unavailable }; emit(); return;
    }
    const errors = validateAuth(action, input);
    state = { ...state, email: String(input.email || '').trim(), errors, message: '' };
    if (Object.keys(errors).length) { emit(); return; }
    const payload = action === 'password' ? { password: input.password } : { email: state.email };
    if (['login', 'signup'].includes(action)) payload.password = input.password;
    const current = ++generation;
    let loggedIn = false;
    state = { ...state, pending: true, message: 'Please wait…' }; emit();
    try {
      const { status, body } = await request(`/api/auth/${actions[action]}`, payload);
      if (current !== generation) return;
      if (status === 200 && body?.ok === true) {
        loggedIn = action === 'login';
        state.message = ({ login: 'You are signed in.', signup: 'If your address is eligible, check your email for a verification link.',
          verification: 'If a verification message can be sent, you will receive it shortly.', recovery: 'If a reset is available for this address, check your email.',
          password: 'Your password has been updated. Log in again to continue.' })[action];
        // Re-bootstrap before another mutation; login/recovery may rotate session/CSRF.
        state.ready = false; csrf = ''; state.recoveryAllowed = false;
      } else if (status === 401 && action === 'login') state.message = 'The email or password could not be verified. Try again or reset your password.';
      else if (status === 429) state.message = 'Too many attempts. Please wait before trying again.';
      else if (status === 403 || status === 401) { state.message = 'This session or link is no longer valid. Request a fresh link or try again.'; state.ready = false; csrf = ''; }
      else state.message = unavailable;
    } catch { if (current === generation) state.message = unavailable; }
    finally { if (current === generation) { state.pending = false; emit(); } }
    if (current === generation && loggedIn) onLogin();
  }
  return { snapshot, load, submit, leave };
}
