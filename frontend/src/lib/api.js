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

export function curate(prompt) {
  return request('/api/curate', { method: 'POST', body: JSON.stringify({ prompt }) });
}

export function createShare(fits) {
  return request('/api/share', { method: 'POST', body: JSON.stringify({ fits }) });
}

export function loadShare(id) {
  return request(`/api/share/${encodeURIComponent(id)}`);
}
