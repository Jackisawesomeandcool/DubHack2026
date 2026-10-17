import { useState } from 'react';
import GarmentCutout from './GarmentCutout.jsx';
import { formatPrice } from '../lib/haul.js';

// One piece on the board. Hover reveals the price only; click opens the popup.
export default function FashionItem({ item, place, selected, onSelect }) {
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = item.image && !imgFailed;

  const style = {
    left: `${place.x}%`,
    top: `${place.y}%`,
    width: `calc(var(--u) * ${place.w})`,
    zIndex: selected ? 60 : place.z,
  };

  return (
    <button
      type="button"
      className={`item${selected ? ' is-selected' : ''}`}
      style={style}
      aria-label={`${item.name} by ${item.brand}, ${formatPrice(item.price)}`}
      onClick={(e) => onSelect(e.currentTarget)}
    >
      <span className="item__price">{formatPrice(item.price)}</span>
      <span className="item__art">
        {showImage ? (
          <img src={item.image} alt="" draggable="false" onError={() => setImgFailed(true)} />
        ) : (
          <GarmentCutout category={item.category} color={item.color} />
        )}
      </span>
    </button>
  );
}
