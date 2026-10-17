import { useCallback, useEffect, useRef, useState } from 'react';
import FashionItem from './FashionItem.jsx';
import ProductPopup from './ProductPopup.jsx';

// The outfit board. Pieces are real product photos; in edit mode they can be
// dragged anywhere on the board (or off it to remove), swapped from the
// options tray, and removed from the popup.
export default function FashionCanvas({
  items,
  fitKey,
  editable = false,
  onMove,
  onRemove,
  onSelectionChange,
  onDragOutChange,
  swapUi = null,
  loading = false,
  hint = '',
  onHintClick,
}) {
  const ref = useRef(null);
  const [selected, setSelected] = useState(null); // { uid, anchor }
  const [draggingOut, setDraggingOut] = useState(null); // the piece held outside the board

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const { width, height } = el.getBoundingClientRect();
      el.style.setProperty('--u', `${Math.min(width, height * 1.5) / 100}px`);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => setSelected(null), [fitKey]);

  const selectedItem = (selected && items.find((i) => i.uid === selected.uid)) || null;
  useEffect(() => { onSelectionChange?.(selectedItem); }, [selectedItem]); // eslint-disable-line react-hooks/exhaustive-deps

  const close = useCallback(() => setSelected(null), []);

  return (
    <section ref={ref} className={`canvas${loading ? ' is-loading' : ''}${draggingOut ? ' is-dragging-out' : ''}`} aria-label="Outfit board">
      <div className="canvas__stage" key={fitKey}>
        {items.map((item, i) => (
          <FashionItem
            key={item.uid}
            item={item}
            zIndex={10 + i}
            selected={selected?.uid === item.uid}
            draggable={editable}
            swapUi={selected?.uid === item.uid ? swapUi : null}
            canvasRef={ref}
            onMove={onMove}
            onRemove={(it) => { onRemove?.(it); if (selected?.uid === it.uid) close(); }}
            onDragOut={(it) => { setDraggingOut(it); onDragOutChange?.(it); }}
            onSelect={(anchor) => setSelected((cur) => (cur?.uid === item.uid ? null : { uid: item.uid, anchor }))}
          />
        ))}
      </div>

      {editable && <div className="canvas__dropout" aria-hidden="true">release to remove</div>}

      {hint && items.length === 0 && !loading && (
        <p className={`canvas__hint${onHintClick ? ' is-clickable' : ''}`} onClick={onHintClick}>{hint}</p>
      )}

      {loading && (
        <div className="canvas__loading" aria-label="Loading">
          <span /><span /><span />
        </div>
      )}

      {selectedItem && (
        <ProductPopup
          item={selectedItem}
          anchor={selected.anchor}
          onClose={close}
          onRemove={editable ? () => { onRemove?.(selectedItem); close(); } : undefined}
        />
      )}
    </section>
  );
}
