import { useEffect, useLayoutEffect, useRef, useState } from 'react';

const GAP = 12;
const MARGIN = 12;

// Small floating card: name, brand, stock (+ remove when editing).
// Positioned next to the clicked item and clamped inside the viewport.
export default function ProductPopup({ item, anchor, onClose, onRemove }) {
  const ref = useRef(null);
  const [pos, setPos] = useState(null);

  useLayoutEffect(() => {
    if (!anchor || !ref.current) return;
    const a = anchor.getBoundingClientRect();
    const p = ref.current.getBoundingClientRect();
    const vw = window.innerWidth, vh = window.innerHeight;

    let left = a.right + GAP;
    if (left + p.width > vw - MARGIN) left = a.left - p.width - GAP;
    if (left < MARGIN) left = Math.min(Math.max(MARGIN, a.left + a.width / 2 - p.width / 2), vw - p.width - MARGIN);

    let top = a.top + a.height / 2 - p.height / 2;
    top = Math.min(Math.max(MARGIN, top), vh - p.height - MARGIN);
    setPos({ left, top });
  }, [anchor, item]);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    const onDown = (e) => {
      if (ref.current?.contains(e.target) || anchor?.contains(e.target)) return;
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
      <div className="popup__row">
        <div className={`popup__stock${inStock ? '' : ' is-out'}`}>
          <span className="popup__dot" />
          {inStock ? 'In Stock' : 'Out of Stock'}
        </div>
        {onRemove && (
          <button type="button" className="popup__remove" onClick={onRemove}>
            remove
          </button>
        )}
      </div>
    </div>
  );
}
