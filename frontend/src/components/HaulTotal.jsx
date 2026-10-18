import { useEffect, useRef, useState } from 'react';
import { formatPrice } from '../lib/haul.js';

// Total for the current fit. The number swells when the haul gets pricier and
// dips when it gets cheaper. While a piece is being dragged off the board, the
// would-be total appears on the left and the current one is struck out.
export default function HaulTotal({ total, pendingTotal = null, resetKey = '' }) {
  const prev = useRef(total);
  const [anim, setAnim] = useState({ dir: '', n: 0 });
  const previewing = pendingTotal !== null && pendingTotal !== total;

  const lastKey = useRef(resetKey);

  useEffect(() => {
    if (lastKey.current !== resetKey) {
      // A different haul (or a fresh load): take the new total silently.
      lastKey.current = resetKey;
      prev.current = total;
      setAnim((a) => ({ ...a, dir: '' }));
      return undefined;
    }
    if (total === prev.current) return undefined;
    const dir = total > prev.current ? 'up' : 'down';
    prev.current = total;
    setAnim((a) => ({ dir, n: a.n + 1 }));
    const t = setTimeout(() => setAnim((a) => ({ ...a, dir: '' })), 1100); // colour fades back to black
    return () => clearTimeout(t);
  }, [total, resetKey]);

  return (
    <div className={`total${previewing ? ' is-previewing' : ''}`} aria-live="polite">
      {previewing && <span className="total__next">{formatPrice(pendingTotal)}</span>}
      <span className={`total__value${anim.dir ? ` is-${anim.dir}` : ''}`} key={anim.n}>{formatPrice(total)}</span>
      <span className="total__label">total</span>
    </div>
  );
}
