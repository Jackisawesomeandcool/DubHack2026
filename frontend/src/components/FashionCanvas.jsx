import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import FashionItem from './FashionItem.jsx';
import HaulWipe, { randomDirection } from './HaulWipe.jsx';
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
  isFavorite,
  onFavorite,
  tools = null,
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

  // Switching hauls: remember what the board showed, then sweep it away (HaulWipe).
  const stageRef = useRef(null);
  const shown = useRef({ key: fitKey, items });
  const [wipe, setWipe] = useState(null); // { from, dir }
  useLayoutEffect(() => {
    if (fitKey === shown.current.key) { shown.current.items = items; return; }
    const from = shown.current.items;
    shown.current = { key: fitKey, items };
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    setWipe(reduce ? null : { from, dir: randomDirection() });
  }, [fitKey, items]);
  const endWipe = useCallback(() => setWipe(null), []);

  const selectedItem = (selected && items.find((i) => i.uid === selected.uid)) || null;
  useEffect(() => { onSelectionChange?.(selectedItem); }, [selectedItem]); // eslint-disable-line react-hooks/exhaustive-deps

  const close = useCallback(() => setSelected(null), []);

  return (
    <section ref={ref} className={`canvas${loading ? ' is-loading' : ''}${draggingOut ? ' is-dragging-out' : ''}${wipe ? ' is-wiping' : ''}`} aria-label="Outfit board">
      <div className="canvas__stage" key={fitKey} ref={stageRef}>
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

      {wipe && <HaulWipe wipe={wipe} canvasRef={ref} stageRef={stageRef} onDone={endWipe} />}

      {editable && <div className="canvas__dropout" aria-hidden="true">release to remove</div>}

      {tools}

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
          boundsRef={ref}
          favorite={isFavorite ? isFavorite(selectedItem) : null}
          onFavorite={onFavorite ? () => onFavorite(selectedItem) : undefined}
        />
      )}
    </section>
  );
}
