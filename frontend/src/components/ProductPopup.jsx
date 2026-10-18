import { useEffect, useLayoutEffect, useRef, useState } from 'react';

const GAP = 30;
const MARGIN = 12;

function host(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return 'listing'; }
}

// Small floating card: name, brand, stock, link to the listing (+ remove when
// editing). Positioned next to the clicked item and clamped inside the viewport.
// Clicks in the dock (options / finder) keep it open so a swap can be picked.
export default function ProductPopup({ item, anchor, onClose, onRemove, favorite = null, onFavorite }) {
  const ref = useRef(null);
  const [pos, setPos] = useState(null);

  useLayoutEffect(() => {
    if (!anchor || !ref.current) return;
    const a = anchor.getBoundingClientRect();
    const p = ref.current.getBoundingClientRect();
    const vw = window.innerWidth, vh = window.innerHeight;

    let left = a.right + GAP;
    if (left + p.width > vw - MARGIN) left = a.left - p.width - GAP;
    if (left < MARGIN) left = Math.min(Math.max(MARGIN, a.left + a.width / 2 - p.width / 2), vw - p.width - MARGIN);

    let top = a.top + a.height / 2 - p.height / 2;
    top = Math.min(Math.max(MARGIN, top), vh - p.height - MARGIN);
    setPos({ left, top });
  }, [anchor, item]);

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
      <div className="popup__row">
        <div className={`popup__stock${inStock ? '' : ' is-out'}`}>
          <span className="popup__dot" />
          {inStock ? 'In Stock' : 'Out of Stock'}
        </div>
        {onRemove && (
          <button type="button" className="popup__remove" onClick={onRemove}>
            remove
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
