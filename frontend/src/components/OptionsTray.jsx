import { useState } from 'react';
import { formatPrice, itemKey, sameProduct } from '../lib/haul.js';

function OptionChip({ item, onBoard, previewing, swapMode, full, onSwap, onAdd }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
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
    </div>
  );
}

// Options just above the prompt bar.
//   normal:     "+" adds the piece to the board (up to the board limit)
//   swap mode:  (a piece is selected) clicking an option tries it in that
//               piece's spot — keep or undo from the board
export default function OptionsTray({ title, options, loading, error, isOnBoard, previewing, full, swapMode, onSwap, onAdd, onDismiss }) {
  if (!loading && !error && options.length === 0 && !swapMode) return null;

  return (
    <div className="tray" role="region" aria-label="Options">
      {title && <div className="tray__title">{title}</div>}
      {loading && (
        <div className="tray__row">
          {Array.from({ length: 5 }).map((_, i) => (
            <span key={i} className="chip chip--skeleton" style={{ '--delay': `${i * 90}ms` }} />
          ))}
        </div>
      )}
      {!loading && error && <p className="tray__msg">{error}</p>}
      {!loading && !error && options.length === 0 && <p className="tray__msg">no alternatives found — try a search below</p>}
      {!loading && !error && options.length > 0 && (
        <div className="tray__row">
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
            />
          ))}
        </div>
      )}
      {!loading && !error && full && !swapMode && <p className="tray__note">board is full — select a piece to swap it</p>}
      <button type="button" className="tray__close" onClick={onDismiss} aria-label="Dismiss options">
        ×
      </button>
    </div>
  );
}
