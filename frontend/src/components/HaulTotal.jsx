import { formatPrice } from '../lib/haul.js';

export default function HaulTotal({ total }) {
  return (
    <div className="total" aria-live="polite">
      <span className="total__value" key={total}>{formatPrice(total)}</span>
      <span className="total__label">TOTAL</span>
    </div>
  );
}
