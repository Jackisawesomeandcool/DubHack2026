import { useRef, useState } from 'react';
import { formatPrice } from '../lib/haul.js';
import { placeFor } from '../lib/layout.js';

const DRAG_THRESHOLD = 4; // px before a press becomes a drag instead of a click

// One piece on the board: a real product photo. Hover reveals the price only;
// click opens the popup; press-and-move drags it (when draggable).
export default function FashionItem({ item, zIndex, selected, draggable, onSelect, onMove, canvasRef }) {
  const [failed, setFailed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const drag = useRef(null);

  if (failed) return null; // never substitute a fake visual

  const w = placeFor(item.category).w;

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
    const x = Math.min(96, Math.max(4, d.x + (dx / d.canvas.width) * 100));
    const y = Math.min(96, Math.max(4, d.y + (dy / d.canvas.height) * 100));
    onMove(item, x, y);
  }

  function onPointerUp(e) {
    const d = drag.current;
    drag.current = null;
    setDragging(false);
    if (!d || !d.moved) onSelect(e.currentTarget);
  }

  return (
    <button
      type="button"
      className={`item${selected ? ' is-selected' : ''}${dragging ? ' is-dragging' : ''}${draggable ? ' is-draggable' : ''}`}
      style={{ left: `${item.x}%`, top: `${item.y}%`, width: `calc(var(--u) * ${w})`, zIndex: dragging || selected ? 60 : zIndex }}
      aria-label={`${item.name} by ${item.brand}, ${formatPrice(item.price)}`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={() => { drag.current = null; setDragging(false); }}
    >
      <span className="item__price">{formatPrice(item.price)}</span>
      <span className="item__art">
        <img src={item.image} alt="" draggable="false" onError={() => setFailed(true)} />
      </span>
    </button>
  );
}
