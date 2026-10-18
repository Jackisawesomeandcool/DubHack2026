// Accounts live on the backend (backend/data/users.sqlite, see backend/auth.py).
// The browser keeps only a session token and a cached copy of the signed-in
// user so pages can render the name before the backend answers.

const USER = 'haul:user';
const TOKEN = 'haul:token';
const GUEST = 'haul:guest';

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}
function write(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch { /* private mode: the session lasts for this page view */ }
}

export const USERNAME_RE = /^[a-z0-9_.]{3,20}$/;

// Usernames are stored lowercase without a leading "@".
export function cleanUsername(value) {
  return value.trim().replace(/^@/, '').toLowerCase();
}

export function token() {
  return read(TOKEN, null);
}

export function loadUser() {
  return read(USER, null);
}

async function call(path, body) {
  const res = await fetch(`/api/auth/${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', ...(token() ? { Authorization: `Bearer ${token()}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function startSession({ user, token: t }) {
  write(USER, user);
  write(TOKEN, t);
  write(GUEST, null);
  return user;
}

// Email or username + password. Throws with a readable message on failure.
export async function logIn(identifier, password) {
  return startSession(await call('login', { identifier: identifier.trim(), password }));
}

export async function signUp({ firstName, username, email, password }) {
  return startSession(await call('signup', { firstName: firstName.trim(), username: cleanUsername(username), email: email.trim(), password }));
}

export async function logOut() {
  try { if (token()) await call('logout', {}); } catch { /* the token is dropped either way */ }
  write(USER, null);
  write(TOKEN, null);
  write(GUEST, null);
}

// Ask the backend who this token belongs to; drops the session if it's stale.
export async function refreshUser() {
  if (!token()) return null;
  try {
    const { user } = await call('me');
    write(USER, user);
    return user;
  } catch {
    write(USER, null);
    write(TOKEN, null);
    return null;
  }
}

export function continueAsGuest() {
  write(GUEST, true);
}

export function isGuest() {
  return read(GUEST, false) === true;
}

// Signed in or chose guest: either way they may use the builder.
export function hasSession() {
  return (Boolean(loadUser()) && Boolean(token())) || isGuest();
}

export function go(path) {
  window.location.assign(path);
}
