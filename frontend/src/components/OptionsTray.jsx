import { useState } from 'react';
import { formatPrice, itemKey } from '../lib/haul.js';

function OptionChip({ item, onBoard, swapMode, full, onSwap, onAdd }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  const canAdd = !onBoard && !full;
  const label = onBoard ? 'On board' : swapMode ? 'Swap in' : 'Add';
  return (
    <div className={`chip${onBoard ? ' is-on' : ''}${swapMode && !onBoard ? ' is-swap' : ''}`}>
      <button
        type="button"
        className="chip__main"
        disabled={onBoard || (!swapMode && !canAdd)}
        onClick={() => (swapMode ? onSwap(item) : onAdd(item))}
        aria-label={`${label}: ${item.name}, ${formatPrice(item.price)}`}
      >
        <span className="chip__art">
          <img src={item.image} alt="" draggable="false" onError={() => setFailed(true)} />
        </span>
        <span className="chip__price">{formatPrice(item.price)}</span>
        {swapMode && !onBoard && <span className="chip__swap">swap</span>}
      </button>
      <button
        type="button"
        className={`chip__badge${onBoard ? ' is-on' : ''}`}
        disabled={!canAdd}
        onClick={() => onAdd(item)}
        aria-label={onBoard ? 'Already on board' : full ? 'Board is full' : `Add ${item.name} to board`}
      >
        {onBoard ? '✓' : '+'}
      </button>
    </div>
  );
}

// Options from the finder, just above the prompt bar.
//   "+"  adds the piece to the board (up to the board limit)
//   chip with a piece selected on the board swaps that piece out
export default function OptionsTray({ options, loading, error, boardKeys, full, swapMode, onSwap, onAdd, onDismiss }) {
  if (!loading && !error && options.length === 0) return null;

  return (
    <div className="tray" role="region" aria-label="Options">
      {loading && (
        <div className="tray__row">
          {Array.from({ length: 5 }).map((_, i) => (
            <span key={i} className="chip chip--skeleton" style={{ '--delay': `${i * 90}ms` }} />
          ))}
        </div>
      )}
      {!loading && error && <p className="tray__msg">{error}</p>}
      {!loading && !error && (
        <div className="tray__row">
          {options.map((item) => (
            <OptionChip
              key={itemKey(item)}
              item={item}
              onBoard={boardKeys.has(itemKey(item))}
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
