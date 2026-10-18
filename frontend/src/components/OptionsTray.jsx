import { useEffect, useRef, useState } from 'react';
import { formatPrice, itemKey, sameProduct } from '../lib/haul.js';

function OptionChip({ item, onBoard, previewing, swapMode, full, onSwap, onAdd, onUnfavorite }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  if (item.pending) {
    return (
      <div className="chip chip--pending" aria-label={`Finding photo for ${item.name}`}>
        <span className="chip__pendingname">{item.name}</span>
      </div>
    );
  }
  const isPreview = previewing && sameProduct(previewing, item);
  const canAdd = !onBoard && !full;
  const label = isPreview ? 'Trying' : onBoard ? 'On board' : swapMode ? 'Try' : 'Add';
  return (
    <div className={`chip${onBoard && !isPreview ? ' is-on' : ''}${isPreview ? ' is-preview' : ''}${swapMode && !onBoard ? ' is-swap' : ''}`}>
      <button
        type="button"
        className="chip__main"
        disabled={(onBoard && !swapMode) || (!swapMode && !canAdd)}
        onClick={() => (swapMode ? onSwap(item) : onAdd(item))}
        aria-label={`${label}: ${item.name}, ${formatPrice(item.price)}`}
      >
        <span className="chip__art">
          <img src={item.image} alt="" draggable="false" onError={() => setFailed(true)} />
        </span>
        <span className="chip__price">{formatPrice(item.price)}</span>
        {swapMode && !onBoard && <span className="chip__swap">try</span>}
      </button>
      {!swapMode && (
        <button
          type="button"
          className={`chip__badge${onBoard ? ' is-on' : ''}`}
          disabled={!canAdd}
          onClick={() => onAdd(item)}
          aria-label={onBoard ? 'Already on board' : full ? 'Board is full' : `Add ${item.name} to board`}
        >
          {onBoard ? '✓' : '+'}
        </button>
      )}
      {isPreview && <span className="chip__badge is-preview" aria-hidden="true">●</span>}
      {onUnfavorite && (
        <button type="button" className="chip__unfav" onClick={() => onUnfavorite(item)} aria-label={`Remove ${item.name} from favorites`} title="Remove from favorites">
          <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M12 2.8l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.7l-5.9 3.1 1.2-6.5L2.5 9.7l6.6-.9z" fill="currentColor" /></svg>
        </button>
      )}
    </div>
  );
}

// Options just above the prompt bar.
//   normal:     "+" adds the piece to the board (up to the board limit)
//   swap mode:  (a piece is selected) clicking an option tries it in that
//               piece's spot — keep or undo from the board
export default function OptionsTray({ title, options, loading, error, isOnBoard, previewing, full, swapMode, onSwap, onAdd, onDismiss, favMode = false, favCount = 0, onToggleFavMode, onUnfavorite }) {
  const row = useRef(null);
  const [scroll, setScroll] = useState({ left: false, right: false });

  // Show ‹ › only when the row actually overflows, and only on the side with more.
  useEffect(() => {
    const el = row.current;
    if (!el) return undefined;
    const update = () => setScroll({ left: el.scrollLeft > 4, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
    update();
    el.addEventListener('scroll', update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => { el.removeEventListener('scroll', update); ro.disconnect(); };
  }, [options, loading]);
  const nudge = (dir) => row.current?.scrollBy({ left: dir * Math.max(200, row.current.clientWidth * 0.7), behavior: 'smooth' });

  if (!loading && !error && options.length === 0 && !swapMode && !favMode) return null;

  return (
    <div className="tray" role="region" aria-label="Options">
      <div className="tray__head">
        {title && <div className="tray__title">{title}</div>}
        {onToggleFavMode && (
          <button type="button" className={`tray__favs${favMode ? ' is-on' : ''}`} onClick={onToggleFavMode} aria-pressed={favMode}>
            <span aria-hidden="true">★</span> {favMode ? 'back to suggestions' : `swap to favorites${favCount ? ` (${favCount})` : ''}`}
          </button>
        )}
      </div>
      {loading && (
        <div className="tray__row">
          {Array.from({ length: 5 }).map((_, i) => (
            <span key={i} className="chip chip--skeleton" style={{ '--delay': `${i * 90}ms` }} />
          ))}
        </div>
      )}
      {!loading && error && <p className="tray__msg">{error}</p>}
      {!loading && !error && options.length === 0 && (
        <p className="tray__msg">{favMode ? 'no favorites yet — click a piece and tap the ★ on its card' : 'no alternatives found — try a search below'}</p>
      )}
      {!loading && !error && options.length > 0 && (
        <div className={`tray__scroller${scroll.left ? ' has-left' : ''}${scroll.right ? ' has-right' : ''}`}>
          <button type="button" className="tray__nav tray__nav--prev" onClick={() => nudge(-1)} aria-label="Scroll left" tabIndex={scroll.left ? 0 : -1}>‹</button>
          <div className="tray__row" ref={row}>
          {options.map((item) => (
            <OptionChip
              key={itemKey(item)}
              item={item}
              onBoard={isOnBoard(item)}
              previewing={previewing}
              swapMode={swapMode}
              full={full}
              onSwap={onSwap}
              onAdd={onAdd}
              onUnfavorite={favMode ? onUnfavorite : undefined}
            />
          ))}
          </div>
          <button type="button" className="tray__nav tray__nav--next" onClick={() => nudge(1)} aria-label="Scroll right" tabIndex={scroll.right ? 0 : -1}>›</button>
        </div>
      )}
      {!loading && !error && full && !swapMode && <p className="tray__note">board is full — select a piece to swap it</p>}
      <button type="button" className="tray__close" onClick={onDismiss} aria-label="Dismiss options">
        ×
      </button>
    </div>
  );
}
