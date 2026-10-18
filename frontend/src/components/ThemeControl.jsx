import { useEffect, useRef, useState } from 'react';
import { THEMES, setTheme, useTheme } from '../lib/theme.js';

// Theme button + swatch menu. Each swatch is drawn with the CSS variables of its own
// data-theme, so the palettes are defined once (styles.css) and the preview can't drift.
export default function ThemeControl() {
  const theme = useTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const btn = useRef(null);
  const current = THEMES.find((t) => t.id === theme) || THEMES[0];

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => {
      if (e.key === 'Escape') { setOpen(false); btn.current?.focus(); }
    };
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey);
    // focus the active option so arrow keys work straight away
    ref.current?.querySelector('[aria-checked="true"]')?.focus();
    return () => { window.removeEventListener('pointerdown', onDown); window.removeEventListener('keydown', onKey); };
  }, [open]);

  function onMenuKey(e) {
    const keys = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
    if (!(e.key in keys)) return;
    e.preventDefault();
    const items = [...ref.current.querySelectorAll('[role="menuitemradio"]')];
    const i = items.indexOf(document.activeElement);
    items[(i + keys[e.key] + items.length) % items.length]?.focus();
  }

  return (
    <div className="theme" ref={ref}>
      <button
        ref={btn}
        type="button"
        className={`theme__btn${open ? ' is-open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Color theme: ${current.name}`}
      >
        <span className="theme__dot" data-theme={current.id} aria-hidden="true" />
        <span className="theme__label">Theme</span>
      </button>
      {open && (
        <div className="theme__menu" role="menu" aria-label="Color theme" onKeyDown={onMenuKey}>
          {THEMES.map((t) => (
            <button
              key={t.id}
              type="button"
              role="menuitemradio"
              aria-checked={t.id === theme}
              className={`theme__opt${t.id === theme ? ' is-on' : ''}`}
              onClick={() => { setTheme(t.id); setOpen(false); btn.current?.focus(); }}
            >
              <span className="theme__sw" data-theme={t.id} aria-hidden="true"><i /><i /><i /></span>
              <span className="theme__txt"><strong>{t.name}</strong><small>{t.note}</small></span>
              <svg className="theme__tick" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                <path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
