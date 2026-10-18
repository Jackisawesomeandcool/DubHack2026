// Demo-only accounts. Nothing here talks to the backend: the "user" is just
// a name + email kept in this browser so the app can greet people and route
// them through log in / sign up / pick vibes. Real auth would replace this file.

const USER = 'haul:user';
const ACCOUNTS = 'haul:accounts'; // everyone who signed up in this browser
const GUEST = 'haul:guest';
const VIBES = 'haul:vibes';
const VIBES_PENDING = 'haul:vibes-pending';

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
  } catch { /* private mode: the demo still works for this page view */ }
}

export function loadUser() {
  return read(USER, null);
}

export const USERNAME_RE = /^[a-z0-9_.]{3,20}$/;

// Usernames are stored lowercase without a leading "@".
export function cleanUsername(value) {
  return value.trim().replace(/^@/, '').toLowerCase();
}

// "Log in": any email or username works. If it matches an account that signed
// up in this browser we use its details; otherwise we make one up (demo only).
export function logIn(identifier) {
  const id = identifier.trim();
  const isEmail = id.includes('@') && !id.startsWith('@');
  const handle = isEmail ? '' : cleanUsername(id);
  const known = read(ACCOUNTS, []).find((a) =>
    isEmail ? a.email.toLowerCase() === id.toLowerCase() : a.username === handle);
  if (known) {
    write(USER, known);
  } else {
    const username = handle || id.split('@')[0].toLowerCase();
    write(USER, { firstName: username, username, email: isEmail ? id : '' });
  }
  write(GUEST, null);
}

export function signUp({ firstName, username, email }) {
  const user = { firstName: firstName.trim(), username: cleanUsername(username), email: email.trim() };
  const others = read(ACCOUNTS, []).filter((a) => a.username !== user.username && a.email !== user.email);
  write(ACCOUNTS, [...others, user]);
  write(USER, user);
  write(GUEST, null);
}

export function logOut() {
  write(USER, null);
  write(GUEST, null);
}

export function continueAsGuest() {
  write(GUEST, true);
}

export function isGuest() {
  return read(GUEST, false) === true;
}

// Signed in or chose guest: either way they may use the builder.
export function hasSession() {
  return Boolean(loadUser()) || isGuest();
}

export function loadVibes() {
  return read(VIBES, []);
}

// Saved from onboarding; HaulCreator turns them into one search the first time it opens.
export function saveVibes(vibes) {
  write(VIBES, vibes);
  write(VIBES_PENDING, vibes.length > 0);
}

export function takeVibePrompt() {
  if (!read(VIBES_PENDING, false)) return '';
  write(VIBES_PENDING, null);
  const vibes = loadVibes();
  return vibes.length ? `${vibes.join(', ')} pieces` : '';
}

export function go(path) {
  window.location.assign(path);
}
