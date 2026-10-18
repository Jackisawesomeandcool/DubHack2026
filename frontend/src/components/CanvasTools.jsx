import { useEffect, useRef, useState } from 'react';

// Two round buttons in the board's bottom-right corner.
//   clear:     first click turns it into a red "clear fit N?" pill, a second click empties
//              this fit only (other fits are untouched). Click elsewhere, Esc, or wait to back out.
//   favorites: opens (or closes) the favorites tray directly, no piece needs to be selected.
export default function CanvasTools({ fitLabel, canClear, onClear, favOn, onFavorites }) {
  const [armed, setArmed] = useState(false);
  const clearRef = useRef(null);

  useEffect(() => setArmed(false), [fitLabel]);
  useEffect(() => { if (!canClear) setArmed(false); }, [canClear]);
  useEffect(() => {
    if (!armed) return undefined;
    const onDown = (e) => { if (!clearRef.current?.contains(e.target)) setArmed(false); };
    const onKey = (e) => e.key === 'Escape' && setArmed(false);
    const timer = setTimeout(() => setArmed(false), 4000);
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [armed]);

  const label = fitLabel.toLowerCase();

  return (
    <div className="canvas__tools">
      <button
        ref={clearRef}
        type="button"
        className={`ctool ctool--clear${armed ? ' is-armed' : ''}`}
        disabled={!canClear}
        onClick={() => { if (armed) { setArmed(false); onClear(); } else setArmed(true); }}
        aria-label={armed ? `Confirm: clear everything on ${fitLabel}` : `Clear ${fitLabel}`}
        title={armed ? `Click again to clear ${fitLabel}` : `Clear ${fitLabel}`}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="ctool__label" aria-hidden={!armed}>clear {label}?</span>
      </button>
      <button
        type="button"
        className={`ctool ctool--fav${favOn ? ' is-on' : ''}`}
        onClick={onFavorites}
        aria-pressed={favOn}
        aria-label={favOn ? 'Hide favorites' : 'Show favorites'}
        title={favOn ? 'Hide favorites' : 'Favorites'}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M12 2.8l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.7l-5.9 3.1 1.2-6.5L2.5 9.7l6.6-.9z" fill="currentColor" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );
}
