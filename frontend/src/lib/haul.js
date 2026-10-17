import { placeFor } from './layout.js';

export const MAX_FITS = 5;

export function emptyFit() {
  return { items: [] };
}

export function fitTotal(fit) {
  return (fit?.items || []).reduce((sum, item) => sum + (Number(item.price) || 0), 0);
}

export function formatPrice(value) {
  return `$${Math.round(value).toLocaleString('en-US')}`;
}

export function fitLabel(index) {
  return `FIT ${String(index + 1).padStart(2, '0')}`;
}

export function itemKey(item) {
  return `${item.brand}|${item.name}`;
}

// Give every item a board position (kept if it already has one, e.g. from a share).
export function withPositions(items) {
  const used = {};
  return items.map((item) => {
    if (typeof item.x === 'number' && typeof item.y === 'number') return item;
    const n = used[item.category] || 0;
    used[item.category] = n + 1;
    const p = placeFor(item.category);
    return { ...item, x: p.x + n * 8, y: p.y + n * 6 };
  });
}

// Place an option on the board. If that slot is taken, the new piece inherits
// the old one's position (a swap); otherwise it takes the slot's home position.
export function placeItem(fit, item) {
  const old = fit.items.find((i) => i.category === item.category);
  const rest = fit.items.filter((i) => i !== old);
  const pos = old ? { x: old.x, y: old.y } : placeFor(item.category);
  return { items: [...rest, { ...item, x: pos.x, y: pos.y }] };
}

export function removeItem(fit, item) {
  return { items: fit.items.filter((i) => i !== item) };
}

export function moveItem(fit, item, x, y) {
  // Moving also brings the piece to the front (end of the list).
  const rest = fit.items.filter((i) => i !== item);
  return { items: [...rest, { ...item, x, y }] };
}
