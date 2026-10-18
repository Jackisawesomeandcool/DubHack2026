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
      {!swapMode && !onUnfavorite && (
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
export default function OptionsTray({ title, options, loading, error, isOnBoard, previewing, full, swapMode, onSwap, onAdd, onDismiss, favMode = false, favEmpty = false, noMatch = false, favCount = 0, onToggleFavMode, onUnfavorite }) {
  const row = useRef(null);

  // The row scrolls; ← → move it. In a swap the keys step through the
  // alternatives instead (handled by the board), and the row follows the
  // piece being tried so it never sits off-screen.
  useEffect(() => {
    if (swapMode) return undefined;
    const onKey = (e) => {
      if (e.target.closest?.('input, textarea')) return;
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const el = row.current;
      if (!el || el.scrollWidth <= el.clientWidth) return;
      e.preventDefault();
      el.scrollBy({ left: (e.key === 'ArrowRight' ? 1 : -1) * 220, behavior: 'smooth' });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [swapMode]);
  useEffect(() => {
    if (!previewing || !row.current) return;
    const el = row.current.querySelector('.chip.is-preview');
    el?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
  }, [previewing]);

  if (!loading && !error && options.length === 0 && !swapMode && !favMode) return null;

  return (
    <div className="tray" role="region" aria-label="Options">
      <div className="tray__head">
        {title && <div className="tray__title">{title}</div>}
        <div className="tray__tools">
          {onToggleFavMode && (
            <button type="button" className={`tray__favs${favMode ? ' is-on' : ''}`} onClick={onToggleFavMode} aria-pressed={favMode}>
              {favMode ? 'back to suggestions' : <><span aria-hidden="true">★</span> swap to favorites{favCount ? ` (${favCount})` : ''}</>}
            </button>
          )}
          <button type="button" className="tray__close" onClick={onDismiss} aria-label="Close this and zoom in on the board" title="Close and zoom in on the board">
            <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true">
              <path d="M3 8V3h5M17 12v5h-5M3 3l6 6M17 17l-6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            zoom in
          </button>
        </div>
      </div>
      {loading && (
        <div className="tray__row">
          {Array.from({ length: 5 }).map((_, i) => (
            <span key={i} className="chip chip--skeleton" style={{ '--delay': `${i * 90}ms` }} />
          ))}
        </div>
      )}
      {!loading && error && <p className="tray__msg">{error}</p>}
      {!loading && !error && options.length === 0 && favEmpty && (
        <div className="tray__empty" role="status">
          <span className="tray__emptystar" aria-hidden="true">★</span>
          <strong>No favorites yet</strong>
          <span>Click a piece and tap the ★ on its card, or search below.</span>
        </div>
      )}
      {!loading && !error && options.length === 0 && !favEmpty && noMatch && (
        <div className="tray__empty" role="status">
          <span className="tray__emptystar" aria-hidden="true">∅</span>
          <strong>Nothing similar in the catalog</strong>
          <span>Try a search below, or switch to your favorites.</span>
        </div>
      )}
      {!loading && !error && options.length === 0 && !favEmpty && !noMatch && (
        <p className="tray__msg">no results — try another search</p>
      )}
      {!loading && !error && options.length > 0 && (
        <div className="tray__scroller">
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
        </div>
      )}
      {!loading && !error && full && !swapMode && <p className="tray__note">board is full — select a piece to swap it</p>}
    </div>
  );
}
