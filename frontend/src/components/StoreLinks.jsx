import { useEffect, useRef, useState } from 'react';
import { fitTotal, formatPrice } from '../lib/haul.js';

function host(url) {
  try { return new URL(url).hostname.split('.').slice(-2).join('.'); } catch { return ''; } // us.brandymelville.com -> brandymelville.com
}

// "Store links": a small window (same family as Share) listing every piece on the current board with its
// price, stock and a link to the retailer's listing, plus the total and a copyable shopping list.
export default function StoreLinks({ fit, disabled }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const ref = useRef(null);
  const timer = useRef(null);
  const items = fit?.items || [];

  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('pointerdown', onDown); window.removeEventListener('keydown', onKey); };
  }, [open]);
  useEffect(() => { if (!items.length) setOpen(false); }, [items.length]);

  async function copy() {
    const text = [
      ...items.map((i) => `${i.brand} — ${i.name} (${formatPrice(i.price)})${i.url ? `\n${i.url}` : ''}`),
      `Total: ${formatPrice(fitTotal(fit))}`,
    ].join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 1800);
    } catch { /* clipboard blocked: the links above can still be opened one by one */ }
  }

  return (
    <div className="links" ref={ref}>
      <button
        type="button"
        className={`links__btn${open ? ' is-open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        disabled={disabled || !items.length}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        Store links
      </button>
      {open && (
        <div className="links__menu" role="dialog" aria-label="Store links for this fit">
          <div className="links__head">
            <span>{items.length} piece{items.length === 1 ? '' : 's'} on this board</span>
            <button type="button" className="links__copy" onClick={copy}>{copied ? 'Copied' : 'Copy list'}</button>
          </div>
          <ul className="links__list">
            {items.map((i) => {
              const out = i.stock === 'out_of_stock';
              const row = (
                <>
                  <span className="links__art"><img src={i.image} alt="" draggable="false" /></span>
                  <span className="links__text">
                    <span className="links__name">{i.name}</span>
                    <span className="links__sub">
                      {i.brand}{out && <em className="links__out"> · out of stock</em>}
                    </span>
                  </span>
                  <span className="links__go">
                    <strong>{formatPrice(i.price)}</strong>
                    {i.url && <span>{host(i.url)} ↗</span>}
                  </span>
                </>
              );
              return (
                <li key={i.uid || `${i.brand}|${i.name}`}>
                  {i.url
                    ? <a className="links__row" href={i.url} target="_blank" rel="noopener noreferrer">{row}</a>
                    : <div className="links__row">{row}</div>}
                </li>
              );
            })}
          </ul>
          <div className="links__total"><span>Total</span><strong>{formatPrice(fitTotal(fit))}</strong></div>
        </div>
      )}
    </div>
  );
}
