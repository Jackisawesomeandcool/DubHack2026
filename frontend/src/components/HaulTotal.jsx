import { formatPrice } from '../lib/haul.js';

// Total for the current fit. While a piece is being dragged off the board,
// the would-be total appears on the left and the current one is struck out.
export default function HaulTotal({ total, pendingTotal = null }) {
  const previewing = pendingTotal !== null && pendingTotal !== total;
  return (
    <div className={`total${previewing ? ' is-previewing' : ''}`} aria-live="polite">
      {previewing && <span className="total__next">{formatPrice(pendingTotal)}</span>}
      <span className="total__value" key={total}>{formatPrice(total)}</span>
      <span className="total__label">TOTAL</span>
    </div>
  );
}
