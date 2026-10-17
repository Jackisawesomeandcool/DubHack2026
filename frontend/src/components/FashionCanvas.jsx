import { useCallback, useEffect, useRef, useState } from 'react';
import FashionItem from './FashionItem.jsx';
import ProductPopup from './ProductPopup.jsx';
import { itemKey } from '../lib/haul.js';

// The outfit board. Pieces are real product photos; in edit mode they can be
// dragged anywhere on the board and removed from the popup.
export default function FashionCanvas({ items, fitKey, editable = false, onMove, onRemove, loading = false, hint = '' }) {
  const ref = useRef(null);
  const [selected, setSelected] = useState(null); // { key, anchor }

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

  const close = useCallback(() => setSelected(null), []);
  const selectedItem = selected && items.find((i) => itemKey(i) === selected.key);

  return (
    <section ref={ref} className={`canvas${loading ? ' is-loading' : ''}`} aria-label="Outfit board">
      <div className="canvas__stage" key={fitKey}>
        {items.map((item, i) => (
          <FashionItem
            key={itemKey(item)}
            item={item}
            zIndex={10 + i}
            selected={selected?.key === itemKey(item)}
            draggable={editable}
            canvasRef={ref}
            onMove={onMove}
            onSelect={(anchor) =>
              setSelected((cur) => (cur?.key === itemKey(item) ? null : { key: itemKey(item), anchor }))
            }
          />
        ))}
      </div>

      {hint && items.length === 0 && !loading && <p className="canvas__hint">{hint}</p>}

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
