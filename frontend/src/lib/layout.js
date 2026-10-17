// Outfit collage layout: a compact centered cluster with light overlap,
// in the spirit of Pinterest's styled outfit collages. Positions are the
// item's center in canvas percent; width is in --u units (1% of canvas).

export const SLOT_LAYOUT = {
  outerwear: { x: 31, y: 40, w: 36, z: 10 },
  top:       { x: 57, y: 31, w: 28, z: 12 },
  bottom:    { x: 50, y: 66, w: 24, z: 11 },
  shoes:     { x: 74, y: 74, w: 28, z: 13 },
  bag:       { x: 80, y: 40, w: 19, z: 12 },
  headwear:  { x: 77, y: 13, w: 14, z: 12 },
  accessory: { x: 25, y: 77, w: 15, z: 12 },
};

export function placeFor(category) {
  return SLOT_LAYOUT[category] || SLOT_LAYOUT.accessory;
}
