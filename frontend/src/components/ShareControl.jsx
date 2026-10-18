import { useEffect, useRef, useState } from 'react';
import { createShare } from '../lib/api.js';
import { exportFits, fitLabel, fitTotal, formatPrice } from '../lib/haul.js';

// Share -> tick the hauls to include (current one pre-ticked) -> link is
// created and copied. With a single haul there's nothing to choose, so the
// link is made straight away.
export default function ShareControl({ fits, current, disabled }) {
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState(() => new Set([current]));
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

  const filledIdx = fits.map((f, i) => (f.items.length ? i : -1)).filter((i) => i >= 0);
  const chosen = filledIdx.filter((i) => picked.has(i));
  const allChosen = chosen.length === filledIdx.length;

  async function share(selection) {
    setOpen(false);
    if (state === 'busy' || !selection.length) return;
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
    if (filledIdx.length <= 1) return share(filledIdx.map((i) => fits[i])); // nothing to choose between
    if (!open) setPicked(new Set([current]));
    setOpen((o) => !o);
  }

  function toggle(i) {
    setPicked((p) => { const n = new Set(p); n.has(i) ? n.delete(i) : n.add(i); return n; });
  }

  const label = { idle: 'Share', busy: '…', copied: 'Link copied', link: 'Link ready', error: 'Try again' }[state];

  return (
    <div className="share" ref={ref}>
      <button
        type="button"
        className={`share__btn${state === 'copied' ? ' is-done' : ''}${open ? ' is-open' : ''}`}
        onClick={onClick}
        disabled={disabled || state === 'busy'}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        {label}
      </button>
      {open && (
        <div className="share__menu" role="dialog" aria-label="Choose fits to share">
          <div className="share__head">
            <span>Share which fits?</span>
            <button type="button" className="share__all" onClick={() => setPicked(new Set(allChosen ? [] : filledIdx))}>
              {allChosen ? 'none' : 'all'}
            </button>
          </div>
          {filledIdx.map((i) => (
            <label key={i} className={`share__opt share__pick${picked.has(i) ? ' is-on' : ''}`}>
              <input type="checkbox" checked={picked.has(i)} onChange={() => toggle(i)} />
              <span className="share__box" aria-hidden="true" />
              <span>{fitLabel(i)}{i === current ? ' · current' : ''}</span>
              <small>{fits[i].items.length} pieces · {formatPrice(fitTotal(fits[i]))}</small>
            </label>
          ))}
          <button type="button" className="share__go" disabled={!chosen.length} onClick={() => share(chosen.map((i) => fits[i]))}>
            {chosen.length ? `Copy link · ${chosen.length} fit${chosen.length > 1 ? 's' : ''}` : 'Pick at least one'}
          </button>
        </div>
      )}
      {state === 'link' && (
        <input className="share__link" readOnly value={link} onFocus={(e) => e.target.select()} />
      )}
    </div>
  );
}
