export const MAX_FITS = 5;

export function emptyFit() {
  return { items: [] };
}

export function fitTotal(fit) {
  return (fit?.items || []).reduce((sum, item) => sum + (Number(item.price) || 0), 0);
}

export function formatPrice(value) {
  const rounded = Math.round(value);
  return `$${rounded.toLocaleString('en-US')}`;
}

export function fitLabel(index) {
  return `FIT ${String(index + 1).padStart(2, '0')}`;
}
