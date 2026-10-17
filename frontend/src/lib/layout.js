// Default outfit collage positions: a compact centered cluster with light
// overlap, in the spirit of Pinterest's styled outfit collages. x/y are the
// piece's center in canvas percent; w is its width in --u units (1% of canvas).

export const SLOT_LAYOUT = {
  outerwear: { x: 31, y: 40, w: 34 },
  top:       { x: 57, y: 31, w: 26 },
  bottom:    { x: 50, y: 66, w: 22 },
  shoes:     { x: 74, y: 74, w: 26 },
  bag:       { x: 80, y: 40, w: 18 },
  headwear:  { x: 77, y: 13, w: 14 },
  accessory: { x: 25, y: 77, w: 15 },
};

export function placeFor(category) {
  return SLOT_LAYOUT[category] || SLOT_LAYOUT.accessory;
}
