export const MAX_FITS = 5;

// One piece per slot, like a Pinterest "styled for you" outfit collage.
export const SLOTS = ['outerwear', 'top', 'bottom', 'shoes', 'bag', 'headwear', 'accessory'];

export const SLOT_LABEL = {
  outerwear: 'jacket',
  top: 'top',
  bottom: 'bottoms',
  shoes: 'shoes',
  bag: 'bag',
  headwear: 'hat',
  accessory: 'accessory',
};

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

// Place an item in its slot, replacing whatever was there.
export function placeItem(fit, item) {
  const items = fit.items.filter((i) => i.category !== item.category);
  return { items: [...items, item] };
}

export function removeItem(fit, item) {
  return { items: fit.items.filter((i) => i !== item) };
}

export function itemKey(item) {
  return `${item.brand}|${item.name}`;
}
