import { useState } from 'react';
import { formatPrice, itemKey } from '../lib/haul.js';

function OptionChip({ item, onBoard, onPick }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <button
      type="button"
      className={`chip${onBoard ? ' is-on' : ''}`}
      onClick={() => onPick(item)}
      aria-label={`${onBoard ? 'On board: ' : 'Add '}${item.name}, ${formatPrice(item.price)}`}
    >
      <span className="chip__art">
        <img src={item.image} alt="" draggable="false" onError={() => setFailed(true)} />
      </span>
      <span className="chip__price">{formatPrice(item.price)}</span>
      <span className="chip__badge" aria-hidden="true">{onBoard ? '✓' : '+'}</span>
    </button>
  );
}

// Options from the finder, just above the prompt bar. Pick one to place it on
// the board; it swaps out whatever is in that slot.
export default function OptionsTray({ options, loading, error, boardKeys, onPick, onDismiss }) {
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
            <OptionChip key={itemKey(item)} item={item} onBoard={boardKeys.has(itemKey(item))} onPick={onPick} />
          ))}
        </div>
      )}
      <button type="button" className="tray__close" onClick={onDismiss} aria-label="Dismiss options">
        ×
      </button>
    </div>
  );
}
