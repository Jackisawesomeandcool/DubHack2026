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

// Returns a few real product options for a request (optionally one category).
export function suggest(prompt, category, exclude) {
  return request('/api/suggest', {
    method: 'POST',
    body: JSON.stringify({ prompt, category: category || null, exclude: exclude || [] }),
  });
}

export function createShare(fits) {
  return request('/api/share', { method: 'POST', body: JSON.stringify({ fits }) });
}

export function loadShare(id) {
  return request(`/api/share/${encodeURIComponent(id)}`);
}

export function randomFit() {
  return request('/api/random-fit');
}
