import { useEffect, useRef, useState } from 'react';
import { formatPrice } from '../lib/haul.js';

// The total swells when the haul gets pricier and dips when it gets cheaper.
// Remounting the number (key) restarts the CSS animation on every change.
export default function HaulTotal({ total }) {
  const prev = useRef(total);
  const [anim, setAnim] = useState({ dir: '', n: 0 });

  useEffect(() => {
    if (total === prev.current) return;
    const dir = total > prev.current ? 'up' : 'down';
    prev.current = total;
    setAnim((a) => ({ dir, n: a.n + 1 }));
  }, [total]);

  return (
    <div className="total" aria-live="polite">
      <span className={`total__value${anim.dir ? ` is-${anim.dir}` : ''}`} key={anim.n}>{formatPrice(total)}</span>
      <span className="total__label">total</span>
    </div>
  );
}
