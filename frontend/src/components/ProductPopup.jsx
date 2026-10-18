import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { aiName } from '../lib/ai.js';

const GAP = 30;
const MARGIN = 12;

function Sparkle() {
  return (
    <svg viewBox="0 0 20 20" width="13" height="13" aria-hidden="true">
      <path d="M10 2.5l1.7 4.6 4.6 1.7-4.6 1.7L10 15.1l-1.7-4.6L3.7 8.8l4.6-1.7z M16 13l.8 2.2 2.2.8-2.2.8L16 19l-.8-2.2-2.2-.8 2.2-.8z" fill="currentColor" />
    </svg>
  );
}

function host(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return 'listing'; }
}

// Small floating card: name, brand, stock, link to the listing (+ remove when
// editing). Positioned next to the clicked item and clamped inside the viewport.
// Clicks in the dock (options / finder) keep it open so a swap can be picked.
export default function ProductPopup({ item, anchor, onClose, onRemove, favorite = null, onFavorite, boundsRef = null }) {
  const ref = useRef(null);
  const [pos, setPos] = useState(null);

  useLayoutEffect(() => {
    if (!anchor || !ref.current) return undefined;
    const place = () => {
      if (!anchor || !ref.current) return;
      const a = anchor.getBoundingClientRect();
      const p = ref.current.getBoundingClientRect();
      // Stay inside the board (so the card never covers the tray or header);
      // fall back to the window when there is no board, e.g. on the guest page.
      const b = boundsRef?.current?.getBoundingClientRect();
      const minX = b ? b.left + MARGIN : MARGIN, maxX = b ? b.right - MARGIN : window.innerWidth - MARGIN;
      const minY = b ? b.top + MARGIN : MARGIN, maxY = b ? b.bottom - MARGIN : window.innerHeight - MARGIN;

      let left = a.right + GAP;
      if (left + p.width > maxX) left = a.left - p.width - GAP;
      if (left < minX) left = Math.min(Math.max(minX, a.left + a.width / 2 - p.width / 2), maxX - p.width);

      let top = a.top + a.height / 2 - p.height / 2;
      top = Math.min(Math.max(minY, top), maxY - p.height);
      setPos({ left, top });
    };
    place();
    // The board shrinks when the tray opens under it: follow it.
    const ro = new ResizeObserver(place);
    if (boundsRef?.current) ro.observe(boundsRef.current);
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [anchor, item, boundsRef]);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    const onDown = (e) => {
      if (ref.current?.contains(e.target) || anchor?.contains(e.target)) return;
      if (e.target.closest?.('.dock') || e.target.closest?.('.item__arrow') || e.target.closest?.('.item__actions')) return;
      onClose();
    };
    const onResize = () => onClose();
    window.addEventListener('keydown', onKey);
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('resize', onResize);
    };
  }, [anchor, onClose]);

  const inStock = item.stock !== 'out_of_stock';

  return (
    <div
      ref={ref}
      className="popup"
      role="dialog"
      aria-label={item.name}
      style={pos ? { left: pos.left, top: pos.top, visibility: 'visible' } : { visibility: 'hidden' }}
    >
      <div className="popup__name">{item.name}</div>
      <div className="popup__brand">{item.brand}</div>
      {aiName(item) && (
        <div className="popup__ai">
          <span className="popup__ai-tag"><Sparkle />Suggested by {aiName(item)}!</span>
          {item.why && <p className="popup__ai-why">{item.why}</p>}
        </div>
      )}
      <div className="popup__row">
        <div className={`popup__stock${inStock ? '' : ' is-out'}`}>
          <span className="popup__dot" />
          {inStock ? 'In Stock' : 'Out of Stock'}
        </div>
        {onRemove && (
          <button type="button" className="popup__remove" onClick={onRemove} aria-label="Remove from the fit" title="Remove from the fit">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
      </div>
      <div className="popup__foot">
      {item.url && (
        <a className="popup__link" href={item.url} target="_blank" rel="noopener noreferrer">
          view on {host(item.url)} ↗
        </a>
      )}
      {onFavorite && (
        <button
          type="button"
          className={`popup__star${favorite ? ' is-on' : ''}`}
          onClick={onFavorite}
          aria-pressed={Boolean(favorite)}
          aria-label={favorite ? 'Remove from favorites' : 'Add to favorites'}
          title={favorite ? 'Favorited' : 'Favorite'}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M12 2.8l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.7l-5.9 3.1 1.2-6.5L2.5 9.7l6.6-.9z" fill={favorite ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          </svg>
        </button>
      )}
      </div>
    </div>
  );
}
