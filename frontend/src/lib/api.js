// All AI and sharing requests go through the Python backend. No secrets here.

async function request(path, options) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

// Streams product options for a request. `onUpdate(items)` is called with the
// current list every time something changes: first the products (no images),
// then as each cutout arrives (items without a usable photo are removed).
// Resolves with the final list.
export async function suggest(prompt, category, exclude, onUpdate, models = false) {
  const res = await fetch('/api/suggest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, category: category || null, exclude: exclude || [], models }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || `Request failed (${res.status})`);
  }

  let items = [];
  const emit = () => onUpdate?.(items.filter((i) => !i.dropped));
  const handle = (ev) => {
    if (ev.items) items = [...items, ...ev.items.map((i) => ({ ...i, pending: !i.image }))]; // catalog hits: ready
    else if (ev.append) items = [...items, ...ev.append.map((i) => ({ ...i, pending: true }))]; // live: photos follow
    else if (ev.image) items[ev.index] = { ...items[ev.index], image: ev.image, pending: false };
    else if (ev.drop) items[ev.index] = { ...items[ev.index], dropped: true };
    emit();
  };

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) handle(JSON.parse(line));
    }
  }
  if (buf.trim()) handle(JSON.parse(buf));
  return items.filter((i) => !i.dropped && !i.pending);
}

export function createShare(fits) {
  return request('/api/share', { method: 'POST', body: JSON.stringify({ fits }) });
}

export function loadShare(id) {
  return request(`/api/share/${encodeURIComponent(id)}`);
}

// Fire-and-forget: ask the backend to re-verify stock for products in play.
export function seen(items) {
  const urls = items.map((i) => i.url).filter(Boolean);
  if (!urls.length) return;
  fetch('/api/seen', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ urls }) }).catch(() => {});
}

export function health() {
  return request('/api/health');
}

export function randomFit(models = false) {
  return request(`/api/random-fit${models ? '?models=1' : ''}`);
}

// Signed-in users: favorites + haul boards live on the backend (users.sqlite).
function authHeaders() {
  try {
    const t = JSON.parse(localStorage.getItem('haul:token') || 'null');
    return t ? { Authorization: `Bearer ${t}` } : {};
  } catch { return {}; }
}

export async function loadState() {
  const res = await fetch('/api/me/state', { headers: authHeaders() });
  if (!res.ok) return null;
  return res.json();
}

export function saveState(favorites, hauls, history) {
  return fetch('/api/me/state', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ favorites, hauls, history }),
    keepalive: true,
  }).then((r) => r.ok).catch(() => false);
}

// Last-chance save when the tab closes (no headers possible: token in the body).
export function saveStateBeacon(favorites, hauls, history) {
  try {
    const token = JSON.parse(localStorage.getItem('haul:token') || 'null');
    if (!token) return;
    const blob = new Blob([JSON.stringify({ token, favorites, hauls, history })], { type: 'application/json' });
    navigator.sendBeacon('/api/me/state', blob);
  } catch { /* nothing to flush */ }
}
