import { useEffect, useRef, useState } from 'react';
import { browse } from '../lib/api.js';
import { formatPrice, itemKey } from '../lib/haul.js';

const CARD = 128; // px, height of one reel card incl. gap (keep in sync with CSS)

function easeOut(t) { return 1 - Math.pow(1 - t, 3); }

// A single column of random pieces on the right of the board. Scroll (or
// ↑ ↓) to flip through; "spin" pulls a fresh set and the reel whirrs past
// the old ones before landing on the new, like a slot machine.
export default function BrowseColumn({ onPick, swapMode = false }) {
  const [items, setItems] = useState([]);
  const [spinning, setSpinning] = useState(false);
  const [failed, setFailed] = useState(() => new Set());
  const list = useRef(null);
  const raf = useRef(null);

  async function load() {
    try {
      const { items: next } = await browse(24);
      return next;
    } catch {
      return [];
    }
  }

  useEffect(() => { load().then(setItems); }, []);
  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  async function spin() {
    if (spinning) return;
    setSpinning(true);
    const next = await load();
    const el = list.current;
    if (!el || !next.length) { setItems(next); setSpinning(false); return; }
    // Reel: old cards stay above, new ones are appended; we race down to the
    // first new card with an ease-out, then quietly drop the old ones.
    const oldCount = items.length;
    setItems([...items, ...next]);
    requestAnimationFrame(() => {
      const start = el.scrollTop;
      const target = oldCount * CARD;
      const distance = target - start;
      const ms = Math.min(2200, 900 + distance * 0.35);
      const t0 = performance.now();
      const tick = (now) => {
        const t = Math.min(1, (now - t0) / ms);
        el.scrollTop = start + distance * easeOut(t);
        if (t < 1) { raf.current = requestAnimationFrame(tick); return; }
        setItems(next);
        requestAnimationFrame(() => { el.scrollTop = 0; setSpinning(false); });
      };
      raf.current = requestAnimationFrame(tick);
    });
  }

  // ↑ ↓ flip the reel one card at a time (when nothing on the page wants the keys).
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest?.('input, textarea')) return;
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
      const el = list.current;
      if (!el) return;
      e.preventDefault();
      el.scrollBy({ top: (e.key === 'ArrowDown' ? 1 : -1) * CARD, behavior: 'smooth' });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const visible = items.filter((i) => !failed.has(itemKey(i)));

  return (
    <aside className={`browse${spinning ? ' is-spinning' : ''}`} aria-label="Browse">
      <div className="browse__head">
        <span className="browse__title">Browse</span>
        <button type="button" className="browse__spin" onClick={spin} disabled={spinning} aria-label="Spin for new pieces" title="Spin">
          <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true">
            <path d="M16 10a6 6 0 1 1-1.8-4.3M16 3v3.5h-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>spin</span>
        </button>
      </div>
      <div className="browse__reel" ref={list}>
        {visible.map((item, i) => (
          <button
            key={`${itemKey(item)}-${i}`}
            type="button"
            className="browse__card"
            onClick={() => !spinning && onPick(item)}
            aria-label={`${swapMode ? 'Try' : 'Add'} ${item.name}, ${formatPrice(item.price)}`}
            title={item.name}
          >
            <img src={item.image} alt="" draggable="false" onError={() => setFailed((f) => new Set(f).add(itemKey(item)))} />
            <span className="browse__price">{formatPrice(item.price)}</span>
            <span className="browse__action" aria-hidden="true">{swapMode ? 'try' : '+'}</span>
          </button>
        ))}
        {visible.length === 0 && <p className="browse__empty">nothing to browse yet</p>}
      </div>
      <div className="browse__fade browse__fade--top" aria-hidden="true" />
      <div className="browse__fade browse__fade--bottom" aria-hidden="true" />
    </aside>
  );
}
