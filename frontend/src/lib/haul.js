import { placeFor } from './layout.js';

export const MAX_FITS = 5;
export const MAX_ITEMS = 12;

let uidCounter = 1;
const uid = () => `p${uidCounter++}`;

let fitCounter = 1;

// Each fit carries a stable id so UI keyed to "which fit" (e.g. the total's
// silent reset) survives deletes and reorders.
export function emptyFit(items = []) {
  return { id: `f${fitCounter++}`, items };
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
  const taken = (x, y) => items.some((i) => Math.abs(i.x - x) < 8 && Math.abs(i.y - y) < 8);
  if (!taken(home.x, home.y)) return home;
  // The home spot is used: fan out around it (second top beside the first, etc.),
  // then anywhere free on the board.
  const ring = [[-18, 0], [18, 0], [0, -20], [0, 20], [-18, -18], [18, 18], [18, -18], [-18, 18], [-30, 0], [30, 0]];
  for (const [dx, dy] of ring) {
    const x = Math.min(90, Math.max(10, home.x + dx)), y = Math.min(90, Math.max(10, home.y + dy));
    if (!taken(x, y)) return { x, y };
  }
  for (let n = 0; n < 40; n++) {
    const x = 12 + Math.random() * 76, y = 12 + Math.random() * 76;
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
  return { ...fit, items: [...fit.items, { ...item, uid: uid(), ...freePosition(fit.items, item.category) }] };
}

// Swap: the new piece takes the selected piece's spot (and id, so the
// selection and position carry over without a flicker).
export function swapItem(fit, oldItem, item) {
  return { ...fit, items: fit.items.map((i) => (i.uid === oldItem.uid ? { ...item, uid: oldItem.uid, x: oldItem.x, y: oldItem.y } : i)) };
}

export function removeItem(fit, item) {
  return { ...fit, items: fit.items.filter((i) => i.uid !== item.uid) };
}

export function moveItem(fit, item, x, y) {
  // Moving also brings the piece to the front (end of the list).
  const rest = fit.items.filter((i) => i.uid !== item.uid);
  return { ...fit, items: [...rest, { ...item, x, y }] };
}

// Strip client-only fields before sharing.
export function exportFits(fits) {
  return fits
    .filter((f) => f.items.length)
    .map((f) => ({ items: f.items.map(({ uid: _uid, ...rest }) => rest) }));
}

// Uncluttered layout for a freshly generated fit: a 3x3 grid of cells, each
// piece goes to the free cell nearest its usual spot (headwear up top, shoes
// at the bottom...), with a little jitter and a smaller size so nothing overlaps.
const CELLS = [20, 50, 80].flatMap((x) => [24, 52, 80].map((y) => ({ x, y })));
const ORDER = ['outerwear', 'top', 'bottom', 'shoes', 'headwear', 'bag', 'accessory'];

export function spreadPositions(items) {
  const uniq = [];
  for (const raw of items) if (!uniq.some((p) => sameProduct(p, raw))) uniq.push({ ...raw, uid: raw.uid || uid() });
  const free = CELLS.slice();
  const rank = (i) => { const n = ORDER.indexOf(i.category); return n < 0 ? ORDER.length : n; };
  return [...uniq].sort((a, b) => rank(a) - rank(b)).map((item) => {
    const home = placeFor(item.category);
    free.sort((a, b) => Math.hypot(a.x - home.x, a.y - home.y) - Math.hypot(b.x - home.x, b.y - home.y));
    const cell = free.shift() || { x: 50, y: 50 };
    const jit = () => (Math.random() - 0.5) * 6;
    return { ...item, x: cell.x + jit(), y: cell.y + jit(), s: 0.8 };
  });
}
