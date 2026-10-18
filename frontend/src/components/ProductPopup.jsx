import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { aiName } from '../lib/ai.js';

const GAP = 14;     // space between the card and the selected piece's controls
const MARGIN = 12;
const MIN_W = 220; // narrowest the card gets when it squeezes in beside a piece

const box = (r) => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
const union = (rs) => rs.reduce((u, r) => ({
  left: Math.min(u.left, r.left), top: Math.min(u.top, r.top), right: Math.max(u.right, r.right), bottom: Math.max(u.bottom, r.bottom),
}));
function overlap(a, b) {
  if (!a || !b) return 0;
  const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  return w > 0 && h > 0 ? w * h : 0;
}
const clamp = (v, lo, hi) => Math.min(Math.max(lo, v), Math.max(lo, hi));

function Sparkle() {
  return (
    <svg viewBox="0 0 20 20" width="13" height="13" aria-hidden="true">
      <path d="M10 2.5l1.7 4.6 4.6 1.7-4.6 1.7L10 15.1l-1.7-4.6L3.7 8.8l4.6-1.7z M16 13l.8 2.2 2.2.8-2.2.8L16 19l-.8-2.2-2.2-.8 2.2-.8z" fill="currentColor" />
    </svg>
  );
}

function host(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return 'listing'; }
}

// Small floating card: name, brand, stock, link to the listing (+ remove when
// editing). Positioned next to the clicked item, clear of its swap controls, inside the board.
// Clicks in the dock (options / finder) keep it open so a swap can be picked.
export default function ProductPopup({ item, anchor, onClose, onRemove, favorite = null, onFavorite, boundsRef = null }) {
  const ref = useRef(null);
  const [pos, setPos] = useState(null);

  // Placement: never on top of the selected piece's own controls (the ‹ › arrows, keep/undo,
  // price tag). Tries beside it (right, then left, narrowing the card if that's what fits),
  // then below / above it, then the board's corners, and takes the first spot that leaves the
  // arrows uncovered; among the rest, the one that covers the least.
  useLayoutEffect(() => {
    if (!anchor || !ref.current) return undefined;
    const itemEl = anchor.closest('.item') || anchor;
    const place = () => {
      const el = ref.current;
      if (!anchor || !el || !anchor.isConnected) return;
      const a = anchor.getBoundingClientRect();
      const rects = (sel) => [...itemEl.querySelectorAll(sel)].map((n) => n.getBoundingClientRect()).filter((r) => r.width && r.height).map(box);
      const arrows = rects('.item__arrow');
      const piece = union([box(a), ...arrows, ...rects('.item__actions, .item__price')]);
      const toolsEl = boundsRef?.current?.querySelector('.canvas__tools');
      const tools = toolsEl ? box(toolsEl.getBoundingClientRect()) : null;
      // Stay inside the board (so the card never covers the tray or header);
      // fall back to the window when there is no board, e.g. on the guest page.
      const b = boundsRef?.current?.getBoundingClientRect();
      const minX = b ? b.left + MARGIN : MARGIN, maxX = b ? b.right - MARGIN : window.innerWidth - MARGIN;
      const minY = b ? b.top + MARGIN : MARGIN, maxY = b ? b.bottom - MARGIN : window.innerHeight - MARGIN;

      // Measure the card at a given width (null = its natural width).
      const sizeAt = (w) => {
        el.style.width = w ? `${w}px` : '';
        el.style.minWidth = w ? '0' : '';
        const r = el.getBoundingClientRect();
        return { w: r.width, h: r.height };
      };
      const natural = sizeAt(null);
      const midY = a.top + a.height / 2, midX = a.left + a.width / 2;
      const spots = [];

      for (const side of ['right', 'left']) {
        const room = side === 'right' ? maxX - (piece.right + GAP) : piece.left - GAP - minX;
        if (room < MIN_W) continue;
        const width = room >= natural.w ? null : Math.floor(room);
        const s = sizeAt(width);
        const left = side === 'right' ? piece.right + GAP : piece.left - GAP - s.w;
        spots.push({ left, top: clamp(midY - s.h / 2, minY, maxY - s.h), width, w: s.w, h: s.h });
      }
      for (const side of ['below', 'above']) {
        const top = side === 'below' ? piece.bottom + GAP : piece.top - GAP - natural.h;
        if (top < minY || top + natural.h > maxY) continue;
        spots.push({ left: clamp(midX - natural.w / 2, minX, maxX - natural.w), top, width: null, ...natural });
      }
      for (const [x, y] of [[maxX - natural.w, minY], [minX, minY], [maxX - natural.w, maxY - natural.h], [minX, maxY - natural.h]]) {
        spots.push({ left: Math.max(minX, x), top: Math.max(minY, y), width: null, ...natural });
      }

      const score = (s) => {
        const r = { left: s.left, top: s.top, right: s.left + s.w, bottom: s.top + s.h };
        return arrows.reduce((n, ar) => n + overlap(r, ar), 0) * 1000 + overlap(r, piece) * 10 + overlap(r, tools);
      };
      let best = spots[0];
      let bestScore = score(best);
      for (const s of spots.slice(1)) {
        if (bestScore === 0) break;
        const sc = score(s);
        if (sc < bestScore) { best = s; bestScore = sc; }
      }
      sizeAt(best.width);
      setPos({ left: best.left, top: best.top });
    };
    place();
    // The board shrinks when the tray opens under it, the piece changes size when a swap
    // loads a new photo, and the arrows / keep-undo appear a moment after selecting: follow all of it.
    const ro = new ResizeObserver(place);
    if (boundsRef?.current) ro.observe(boundsRef.current);
    ro.observe(anchor);
    const mo = new MutationObserver(place);
    mo.observe(itemEl, { childList: true, subtree: true });
    return () => { ro.disconnect(); mo.disconnect(); };
  }, [anchor, item, boundsRef]);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    const onDown = (e) => {
      if (ref.current?.contains(e.target) || anchor?.contains(e.target)) return;
      if (e.target.closest?.('.dock, .item__arrow, .item__actions, .canvas__tools')) return;
      onClose();
    };
    const onResize = () => onClose();
    window.addEventListener('keydown', onKey);
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('pointerdown', onDown);
      window.removeEventListener('resize', onResize);
    };
  }, [anchor, onClose]);

  const inStock = item.stock !== 'out_of_stock';

  return (
    <div
      ref={ref}
      className="popup"
      role="dialog"
      aria-label={item.name}
      style={pos ? { left: pos.left, top: pos.top, visibility: 'visible' } : { visibility: 'hidden' }}
    >
      <div className="popup__name">{item.name}</div>
      <div className="popup__brand">{item.brand}</div>
      {aiName(item) && (
        <div className="popup__ai">
          <span className="popup__ai-tag"><Sparkle />Suggested by {aiName(item)}!</span>
          {item.why && <p className="popup__ai-why">{item.why}</p>}
        </div>
      )}
      <div className="popup__row">
        <div className={`popup__stock${inStock ? '' : ' is-out'}`}>
          <span className="popup__dot" />
          {inStock ? 'In Stock' : 'Out of Stock'}
        </div>
        {onRemove && (
          <button type="button" className="popup__remove" onClick={onRemove} aria-label="Remove from the fit" title="Remove from the fit">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
      </div>
      <div className="popup__foot">
      {item.url && (
        <a className="popup__link" href={item.url} target="_blank" rel="noopener noreferrer">
          view on {host(item.url)} ↗
        </a>
      )}
      {onFavorite && (
        <button
          type="button"
          className={`popup__star${favorite ? ' is-on' : ''}`}
          onClick={onFavorite}
          aria-pressed={Boolean(favorite)}
          aria-label={favorite ? 'Remove from favorites' : 'Add to favorites'}
          title={favorite ? 'Favorited' : 'Favorite'}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M12 2.8l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.7l-5.9 3.1 1.2-6.5L2.5 9.7l6.6-.9z" fill={favorite ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
          </svg>
        </button>
      )}
      </div>
    </div>
  );
}
