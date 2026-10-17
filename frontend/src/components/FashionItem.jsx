import { useRef, useState } from 'react';
import { formatPrice } from '../lib/haul.js';
import { placeFor } from '../lib/layout.js';

const DRAG_THRESHOLD = 4; // px before a press becomes a drag instead of a click

// One piece on the board: a real product cutout. Hover reveals the price only;
// click selects it (popup + swap controls); press-and-move drags it. Dropping
// it outside the board removes it.
export default function FashionItem({ item, zIndex, selected, draggable, swapUi, onSelect, onMove, onDragOut, onRemove, canvasRef }) {
  const [failed, setFailed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [outside, setOutside] = useState(false);
  const drag = useRef(null);

  if (failed) return null; // never substitute a fake visual

  const w = placeFor(item.category).w;

  function isOutside(e, rect) {
    return e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom;
  }

  function onPointerDown(e) {
    if (!draggable || e.button !== 0) return;
    const canvas = canvasRef.current?.getBoundingClientRect();
    if (!canvas) return;
    drag.current = { startX: e.clientX, startY: e.clientY, x: item.x, y: item.y, canvas, moved: false };
    e.currentTarget.setPointerCapture(e.pointerId);
  }

  function onPointerMove(e) {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.startX, dy = e.clientY - d.startY;
    if (!d.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    if (!d.moved) { d.moved = true; setDragging(true); }
    const out = isOutside(e, d.canvas);
    if (out !== d.outside) { d.outside = out; setOutside(out); onDragOut?.(out); }
    onMove(item, d.x + (dx / d.canvas.width) * 100, d.y + (dy / d.canvas.height) * 100);
  }

  function finish(e, cancelled) {
    const d = drag.current;
    drag.current = null;
    setDragging(false);
    setOutside(false);
    onDragOut?.(false);
    if (!d) return;
    if (!d.moved) { if (!cancelled) onSelect(e.currentTarget); return; }
    if (d.outside && !cancelled) { onRemove(item); return; }
    onMove(item, Math.min(96, Math.max(4, item.x)), Math.min(96, Math.max(4, item.y)));
  }

  const stop = (e) => e.stopPropagation();
  const cls = ['item', selected && 'is-selected', dragging && 'is-dragging', outside && 'is-leaving', draggable && 'is-draggable', swapUi?.dirty && 'is-dirty']
    .filter(Boolean).join(' ');

  return (
    <div
      className={cls}
      style={{ left: `${item.x}%`, top: `${item.y}%`, width: `calc(var(--u) * ${w})`, zIndex: dragging || selected ? 60 : zIndex }}
    >
      <button
        type="button"
        className="item__hit"
        aria-label={`${item.name} by ${item.brand}, ${formatPrice(item.price)}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={(e) => finish(e, false)}
        onPointerCancel={(e) => finish(e, true)}
      >
        <span className="item__price">{formatPrice(item.price)}</span>
        <span className="item__art">
          <img key={item.image} src={item.image} alt="" draggable="false" onError={() => setFailed(true)} />
        </span>
      </button>

      {selected && swapUi && (
        <>
          <button type="button" className="item__arrow item__arrow--prev" onPointerDown={stop} onClick={swapUi.onPrev} disabled={!swapUi.canPrev} aria-label="Previous alternative">‹</button>
          <button type="button" className="item__arrow item__arrow--next" onPointerDown={stop} onClick={swapUi.onNext} disabled={!swapUi.canNext} aria-label="Next alternative">›</button>
          <div className="item__actions" onPointerDown={stop}>
            {swapUi.loading && !swapUi.dirty && <span className="item__hintpill">finding alternatives…</span>}
            {!swapUi.loading && !swapUi.dirty && swapUi.canNext && <span className="item__hintpill">‹ › to try others</span>}
            {swapUi.dirty && (
              <>
                <button type="button" className="item__keep" onClick={swapUi.onKeep}>keep</button>
                <button type="button" className="item__undo" onClick={swapUi.onUndo}>undo</button>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
