import { MAX_FITS, fitLabel } from '../lib/haul.js';

// Tab-like fit switcher with a single clear selected state.
export default function FitSelector({ fits, current, onSelect, onAdd }) {
  return (
    <nav className="fits" aria-label="Fits">
      {fits.map((_, i) => (
        <button
          key={i}
          type="button"
          className={`fits__tab${i === current ? ' is-active' : ''}`}
          aria-pressed={i === current}
          onClick={() => onSelect(i)}
        >
          <span className="fit__label">{fitLabel(i)}</span>
          <span className="fit__hl" aria-hidden="true">{fitLabel(i)}</span>
        </button>
      ))}
      {onAdd && fits.length < MAX_FITS && (
        <button type="button" className="fits__tab fits__add" onClick={onAdd} aria-label="New fit">
          + FIT
        </button>
      )}
    </nav>
  );
}
