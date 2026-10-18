import { useLayoutEffect, useRef, useState } from 'react';
import { MAX_FITS, fitLabel } from '../lib/haul.js';

// How long the black indicator takes to slide between hauls. It grows slower
// than the distance, so longer jumps (Haul 1 -> 5) move faster per step.
function slideMs(steps) {
  return steps === 0 ? 0 : Math.min(480, Math.round(230 * Math.sqrt(steps)));
}

// Tab-like haul switcher. One black indicator slides behind the active tab.
// The active tab shows a small × to delete that haul (when there's more than one).
export default function FitSelector({ fits, current, onSelect, onAdd, onDelete }) {
  const navRef = useRef(null);
  const prev = useRef(current);
  const [box, setBox] = useState(null); // { x, y, w, h, ms }

  // Measure the active tab; slide there when `current` changes, snap on resize.
  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return undefined;
    const measure = (ms) => {
      const tab = nav.querySelector(`[data-fit="${current}"]`);
      if (!tab) return setBox(null);
      const n = nav.getBoundingClientRect();
      const t = tab.getBoundingClientRect();
      setBox({ x: t.left - n.left, y: t.top - n.top, w: t.width, h: t.height, ms });
    };
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    measure(reduce ? 0 : slideMs(Math.abs(current - prev.current)));
    prev.current = current;
    // Snap (no slide) only when the list itself changes size, e.g. a window resize.
    // ResizeObserver also fires once on observe; that first call must not cancel the slide.
    let size = `${nav.offsetWidth}x${nav.offsetHeight}`;
    const ro = new ResizeObserver(() => {
      const next = `${nav.offsetWidth}x${nav.offsetHeight}`;
      if (next !== size) { size = next; measure(0); }
    });
    ro.observe(nav);
    return () => ro.disconnect();
  }, [current, fits.length]);

  return (
    <nav className="fits" aria-label="Fits" ref={navRef} style={{ '--slide-ms': `${box?.ms || 0}ms` }}>
      {box && (
        <span
          className="fits__indicator"
          aria-hidden="true"
          style={{ width: box.w, height: box.h, transform: `translate(${box.x}px, ${box.y}px)`, transitionDuration: `${box.ms}ms` }}
        />
      )}
      {fits.map((_, i) => (
        <div key={i} className={`fits__item${i === current ? ' is-active' : ''}`}>
          <button
            type="button"
            data-fit={i}
            className={`fits__tab${i === current ? ' is-active' : ''}`}
            aria-pressed={i === current}
            onClick={() => onSelect(i)}
          >
            <span className="fit__label">{fitLabel(i)}</span>
            <span className="fit__hl" aria-hidden="true">{fitLabel(i)}</span>
          </button>
          {onDelete && i === current && fits.length > 1 && (
            <button type="button" className="fits__del" onClick={() => onDelete(i)} aria-label={`Delete ${fitLabel(i)}`} title="Delete this fit">
              ×
            </button>
          )}
        </div>
      ))}
      {onAdd && fits.length < MAX_FITS && (
        <button type="button" className="fits__tab fits__add" onClick={onAdd} aria-label="New fit">
          + New fit
        </button>
      )}
    </nav>
  );
}
