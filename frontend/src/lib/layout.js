// Organic collage placement. Each category has a "home" region of the canvas
// (percentages) and a relative size; a little deterministic jitter keeps every
// fit from looking identical while staying balanced.

const SLOTS = {
  outerwear: [{ x: 18, y: 34, w: 30, r: -4 }, { x: 80, y: 36, w: 28, r: 5 }],
  top:       [{ x: 46, y: 24, w: 22, r: 3 },  { x: 24, y: 28, w: 22, r: -3 }],
  bottom:    [{ x: 50, y: 60, w: 19, r: -2 }, { x: 56, y: 58, w: 19, r: 3 }],
  shoes:     [{ x: 82, y: 76, w: 22, r: 6 },  { x: 20, y: 78, w: 22, r: -6 }],
  bag:       [{ x: 80, y: 30, w: 16, r: 8 },  { x: 82, y: 70, w: 16, r: -8 }],
  accessory: [{ x: 18, y: 76, w: 13, r: -10 }, { x: 68, y: 86, w: 12, r: 12 }],
  headwear:  [{ x: 70, y: 14, w: 13, r: -8 },  { x: 30, y: 12, w: 13, r: 8 }],
};

function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967295;
}

export function layoutItems(items) {
  const used = {};
  return items.map((item, i) => {
    const key = SLOTS[item.category] ? item.category : 'accessory';
    const n = used[key] || 0;
    used[key] = n + 1;
    const slot = SLOTS[key][Math.min(n, SLOTS[key].length - 1)];
    const seed = hash(`${item.brand}|${item.name}|${i}`);
    const jitter = (seed - 0.5) * 4;
    // Later duplicates nudge away so nothing stacks exactly.
    const spread = n >= SLOTS[key].length ? (n - SLOTS[key].length + 1) * 10 : 0;
    return {
      x: slot.x + jitter + spread,
      y: slot.y - jitter,
      w: slot.w,
      r: slot.r + jitter,
      z: 10 + i,
    };
  });
}
