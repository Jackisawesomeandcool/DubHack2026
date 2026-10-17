import { useCallback, useEffect, useRef, useState } from 'react';
import FashionItem from './FashionItem.jsx';
import EmptySlot from './EmptySlot.jsx';
import ProductPopup from './ProductPopup.jsx';
import { placeFor } from '../lib/layout.js';
import { SLOTS, itemKey } from '../lib/haul.js';

// The outfit board. Filled slots show the piece; in edit mode empty slots show a "+".
export default function FashionCanvas({
  items,
  fitKey,
  editable = false,
  focusCategory = null,
  onSlotClick,
  onRemove,
  loading = false,
  hint = '',
}) {
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
  const byCategory = Object.fromEntries(items.map((i) => [i.category, i]));
  const selectedItem = selected && items.find((i) => itemKey(i) === selected.key);

  return (
    <section ref={ref} className="canvas" aria-label="Outfit board">
      <div className="canvas__stage" key={fitKey}>
        {SLOTS.map((cat) => {
          const item = byCategory[cat];
          const place = placeFor(cat);
          if (item) {
            return (
              <FashionItem
                key={itemKey(item)}
                item={item}
                place={place}
                selected={selected?.key === itemKey(item)}
                onSelect={(anchor) =>
                  setSelected((cur) => (cur?.key === itemKey(item) ? null : { key: itemKey(item), anchor }))
                }
              />
            );
          }
          if (!editable) return null;
          return (
            <EmptySlot
              key={`slot-${cat}`}
              category={cat}
              place={place}
              active={focusCategory === cat}
              onClick={() => onSlotClick?.(cat)}
            />
          );
        })}
      </div>

      {hint && items.length === 0 && <p className="canvas__hint">{hint}</p>}

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
