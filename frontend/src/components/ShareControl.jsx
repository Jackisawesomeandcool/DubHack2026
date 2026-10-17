import { useEffect, useRef, useState } from 'react';
import { createShare } from '../lib/api.js';
import { exportFits, fitLabel } from '../lib/haul.js';

// SHARE -> choose this fit or all fits -> link is created and copied.
export default function ShareControl({ fits, current, disabled }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState('idle'); // idle | busy | copied | link | error
  const [link, setLink] = useState('');
  const ref = useRef(null);
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('pointerdown', onDown); window.removeEventListener('keydown', onKey); };
  }, [open]);

  const filled = fits.filter((f) => f.items.length);
  const currentHasItems = fits[current]?.items.length > 0;

  async function share(selection) {
    setOpen(false);
    if (state === 'busy') return;
    setState('busy');
    try {
      const { id } = await createShare(exportFits(selection));
      const url = `${window.location.origin}/h/${id}`;
      setLink(url);
      try {
        await navigator.clipboard.writeText(url);
        setState('copied');
      } catch {
        setState('link'); // clipboard blocked: show the link so it can be copied by hand
      }
    } catch {
      setState('error');
    }
    timer.current = setTimeout(() => setState('idle'), 2600);
  }

  function onClick() {
    if (filled.length <= 1) return share(filled); // nothing to choose between
    setOpen((o) => !o);
  }

  const label = { idle: 'SHARE', busy: '…', copied: 'LINK COPIED', link: 'LINK READY', error: 'TRY AGAIN' }[state];

  return (
    <div className="share" ref={ref}>
      <button
        type="button"
        className={`share__btn${state === 'copied' ? ' is-done' : ''}${open ? ' is-open' : ''}`}
        onClick={onClick}
        disabled={disabled || state === 'busy'}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {label}
      </button>
      {open && (
        <div className="share__menu" role="menu">
          <button type="button" role="menuitem" className="share__opt" disabled={!currentHasItems} onClick={() => share([fits[current]])}>
            <span>this fit</span><small>{fitLabel(current)}</small>
          </button>
          <button type="button" role="menuitem" className="share__opt" onClick={() => share(fits)}>
            <span>all fits</span><small>{filled.length} fits</small>
          </button>
        </div>
      )}
      {state === 'link' && (
        <input className="share__link" readOnly value={link} onFocus={(e) => e.target.select()} />
      )}
    </div>
  );
}
