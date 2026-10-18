import { sameProduct } from './haul.js';

// Starred listings, kept in this browser. Stored without board-only fields.
const KEY = 'haul:favorites';

export function loadFavorites() {
  try {
    const list = JSON.parse(localStorage.getItem(KEY) || '[]');
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function saveFavorites(list) {
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch {}
}

export function isFavorite(list, item) {
  return list.some((f) => sameProduct(f, item));
}

export function toggleFavorite(list, item) {
  if (isFavorite(list, item)) return list.filter((f) => !sameProduct(f, item));
  const { uid: _uid, x: _x, y: _y, pending: _p, dropped: _d, ...clean } = item;
  return [clean, ...list];
}
