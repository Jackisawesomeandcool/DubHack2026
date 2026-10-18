import { MAX_FITS, fitLabel } from '../lib/haul.js';

// Tab-like fit switcher with a single clear selected state. The active tab
// shows a small × to delete that fit (when there's more than one).
export default function FitSelector({ fits, current, onSelect, onAdd, onDelete }) {
  return (
    <nav className="fits" aria-label="Fits">
      {fits.map((_, i) => (
        <div key={i} className={`fits__item${i === current ? ' is-active' : ''}`}>
          <button
            type="button"
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
          + FIT
        </button>
      )}
    </nav>
  );
}
