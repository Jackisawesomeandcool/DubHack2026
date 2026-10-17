import { SLOT_LABEL } from '../lib/haul.js';

// A "+" where a piece can go. Clicking it points the finder at that category.
export default function EmptySlot({ category, place, active, onClick }) {
  const style = {
    left: `${place.x}%`,
    top: `${place.y}%`,
    width: `calc(var(--u) * ${Math.min(place.w, 20)})`,
    zIndex: place.z,
  };
  return (
    <button
      type="button"
      className={`slot${active ? ' is-active' : ''}`}
      style={style}
      aria-label={`Add ${SLOT_LABEL[category]}`}
      onClick={onClick}
    >
      <span className="slot__plus" aria-hidden="true">+</span>
      <span className="slot__label">{SLOT_LABEL[category]}</span>
    </button>
  );
}
