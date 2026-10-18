import { placeFor } from './layout.js';

export const MAX_FITS = 5;
export const MAX_ITEMS = 10;

let uidCounter = 1;
const uid = () => `p${uidCounter++}`;

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
  return `Fit ${index + 1}`;
}

export function itemKey(item) {
  return `${item.brand}|${item.name}`;
}

// Same product if same name+brand, or the very same photo (retailers reuse
// one image across near-identical listings).
export function sameProduct(a, b) {
  return itemKey(a) === itemKey(b) || (Boolean(a.image) && a.image === b.image);
}

export function onBoard(fit, item) {
  return fit.items.some((i) => sameProduct(i, item));
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

// Give every item a stable id and a board position (both kept if present).
export function withPositions(items) {
  const placed = [];
  for (const raw of items) {
    if (placed.some((p) => sameProduct(p, raw))) continue; // drop duplicates
    const item = { ...raw, uid: raw.uid || uid() };
    if (typeof item.x !== 'number' || typeof item.y !== 'number') Object.assign(item, freePosition(placed, item.category));
    placed.push(item);
  }
  return placed;
}

// "+" on an option: add it as another piece (up to MAX_ITEMS).
export function addItem(fit, item) {
  if (fit.items.length >= MAX_ITEMS || onBoard(fit, item)) return fit;
  return { items: [...fit.items, { ...item, uid: uid(), ...freePosition(fit.items, item.category) }] };
}

// Swap: the new piece takes the selected piece's spot (and id, so the
// selection and position carry over without a flicker).
export function swapItem(fit, oldItem, item) {
  if (fit.items.some((i) => i.uid !== oldItem.uid && sameProduct(i, item))) return removeItem(fit, oldItem);
  return { items: fit.items.map((i) => (i.uid === oldItem.uid ? { ...item, uid: oldItem.uid, x: oldItem.x, y: oldItem.y } : i)) };
}

export function removeItem(fit, item) {
  return { items: fit.items.filter((i) => i.uid !== item.uid) };
}

export function moveItem(fit, item, x, y) {
  // Moving also brings the piece to the front (end of the list).
  const rest = fit.items.filter((i) => i.uid !== item.uid);
  return { items: [...rest, { ...item, x, y }] };
}

// Strip client-only fields before sharing.
export function exportFits(fits) {
  return fits
    .filter((f) => f.items.length)
    .map((f) => ({ items: f.items.map(({ uid: _uid, ...rest }) => rest) }));
}
