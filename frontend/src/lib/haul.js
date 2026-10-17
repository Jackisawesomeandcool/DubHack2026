import { placeFor } from './layout.js';

export const MAX_FITS = 5;
export const MAX_ITEMS = 10;

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

// A free position for a new piece: its category's home spot if nothing is
// there yet, otherwise stepped away from it so pieces don't stack exactly.
function freePosition(items, category) {
  const home = placeFor(category);
  const taken = (x, y) => items.some((i) => Math.abs(i.x - x) < 3 && Math.abs(i.y - y) < 3);
  for (let n = 0; n < 12; n++) {
    const x = Math.min(92, home.x + n * 7);
    const y = Math.min(92, home.y + n * 5);
    if (!taken(x, y)) return { x, y };
  }
  return { x: 50, y: 50 };
}

// Give every item a board position (kept if it already has one, e.g. from a share).
export function withPositions(items) {
  const placed = [];
  for (const item of items) {
    if (typeof item.x === 'number' && typeof item.y === 'number') placed.push(item);
    else placed.push({ ...item, ...freePosition(placed, item.category) });
  }
  return placed;
}

// "+" on an option: add it as another piece (up to MAX_ITEMS).
export function addItem(fit, item) {
  if (fit.items.length >= MAX_ITEMS) return fit;
  if (fit.items.some((i) => itemKey(i) === itemKey(item))) return fit;
  return { items: [...fit.items, { ...item, ...freePosition(fit.items, item.category) }] };
}

// Swap: the new piece takes the selected piece's spot on the board.
export function swapItem(fit, oldItem, item) {
  if (fit.items.some((i) => i !== oldItem && itemKey(i) === itemKey(item))) return removeItem(fit, oldItem);
  return { items: fit.items.map((i) => (i === oldItem ? { ...item, x: oldItem.x, y: oldItem.y } : i)) };
}

export function removeItem(fit, item) {
  return { items: fit.items.filter((i) => i !== item) };
}

export function moveItem(fit, item, x, y) {
  // Moving also brings the piece to the front (end of the list).
  const rest = fit.items.filter((i) => i !== item);
  return { items: [...rest, { ...item, x, y }] };
}
