import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import FashionItem from './FashionItem.jsx';
import ProductPopup from './ProductPopup.jsx';
import { layoutItems } from '../lib/layout.js';

// The collage surface. Items float at organic positions; sizes scale with the
// canvas via a --u unit so the composition holds across window sizes.
export default function FashionCanvas({ items, fitKey, busy, emptyHint }) {
  const ref = useRef(null);
  const [selected, setSelected] = useState(null); // { index, anchor }

  const places = useMemo(() => layoutItems(items), [items]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const update = () => {
      const { width, height } = el.getBoundingClientRect();
      el.style.setProperty('--u', `${Math.min(width, height * 1.45) / 100}px`);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Changing fit or regenerating closes any open popup.
  useEffect(() => setSelected(null), [fitKey, items]);

  const close = useCallback(() => setSelected(null), []);
  const select = (index) => (anchor) =>
    setSelected((cur) => (cur?.index === index ? null : { index, anchor }));

  return (
    <section ref={ref} className={`canvas${busy ? ' is-busy' : ''}`} aria-label="Fashion collage">
      <div className="canvas__stage" key={fitKey}>
        {items.map((item, i) => (
          <FashionItem
            key={`${item.brand}-${item.name}-${i}`}
            item={item}
            place={places[i]}
            index={i}
            selected={selected?.index === i}
            onSelect={select(i)}
          />
        ))}
      </div>

      {items.length === 0 && !busy && <p className="canvas__hint">{emptyHint}</p>}

      {busy && (
        <div className="canvas__loading" aria-live="polite" aria-label="Curating">
          <span /><span /><span />
        </div>
      )}

      {selected && items[selected.index] && (
        <ProductPopup item={items[selected.index]} anchor={selected.anchor} onClose={close} />
      )}
    </section>
  );
}
