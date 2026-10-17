// Clean flat garment cutouts, one per category, tinted with the product color.
// Used when a product has no verified image so the collage never shows a
// broken image or a text placeholder.

function shade(hex, amount) {
  const n = parseInt(hex.slice(1), 16);
  const ch = (v) => Math.max(0, Math.min(255, Math.round(v + amount)));
  const r = ch((n >> 16) & 255), g = ch((n >> 8) & 255), b = ch(n & 255);
  return `rgb(${r} ${g} ${b})`;
}

const SHAPES = {
  outerwear: {
    viewBox: '0 0 200 220',
    body: 'M100 18 L132 22 L170 48 L196 120 L166 132 L158 104 L160 206 L40 206 L42 104 L34 132 L4 120 L30 48 L68 22 Z',
    detail: ['M68 22 L100 74 L132 22', 'M100 74 L100 206', 'M40 150 L62 148', 'M160 150 L138 148'],
  },
  top: {
    viewBox: '0 0 200 200',
    body: 'M72 20 Q100 44 128 20 L172 36 L196 94 L162 106 L156 86 L156 184 L44 184 L44 86 L38 106 L4 94 L28 36 Z',
    detail: ['M72 20 Q100 48 128 20'],
  },
  bottom: {
    viewBox: '0 0 160 260',
    body: 'M30 14 L130 14 L136 44 L150 248 L98 252 L80 128 L62 252 L10 248 L24 44 Z',
    detail: ['M30 36 L130 36', 'M80 40 L80 128'],
  },
  shoes: {
    viewBox: '0 0 240 120',
    body: 'M14 78 Q12 40 44 30 L58 14 Q80 10 100 20 L140 56 Q184 70 220 78 Q236 84 232 104 L18 104 Q6 104 14 78 Z',
    detail: ['M14 86 L230 86', 'M64 26 Q96 52 140 56', 'M78 30 L96 44', 'M70 40 L88 54'],
  },
  bag: {
    viewBox: '0 0 200 200',
    body: 'M30 70 L170 70 L186 184 L14 184 Z',
    detail: ['M64 70 Q64 18 100 18 Q136 18 136 70', 'M30 98 L170 98'],
    strokeTop: true,
  },
  accessory: {
    viewBox: '0 0 220 100',
    body: 'M10 42 Q10 18 40 18 L90 18 Q104 18 110 34 Q116 18 130 18 L180 18 Q210 18 210 42 L210 60 Q210 82 180 82 L130 82 Q116 82 110 68 Q104 82 90 82 L40 82 Q10 82 10 60 Z',
    detail: ['M94 50 L126 50'],
  },
  headwear: {
    viewBox: '0 0 220 130',
    body: 'M48 84 Q48 18 110 18 Q172 18 172 84 Z',
    detail: ['M20 84 L200 84 Q212 84 212 94 Q212 104 200 104 L20 104 Q8 104 8 94 Q8 84 20 84 Z'],
    fillDetail: true,
  },
};

export default function GarmentCutout({ category, color = '#b9b4aa' }) {
  const shape = SHAPES[category] || SHAPES.accessory;
  const id = `g-${category}-${color.slice(1)}`;
  return (
    <svg className="cutout" viewBox={shape.viewBox} aria-hidden="true">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={shade(color, 22)} />
          <stop offset="1" stopColor={shade(color, -18)} />
        </linearGradient>
      </defs>
      <path d={shape.body} fill={`url(#${id})`} stroke={shade(color, -40)} strokeWidth="2.5" strokeLinejoin="round" />
      {shape.detail.map((d, i) => (
        <path
          key={i}
          d={d}
          fill={shape.fillDetail ? `url(#${id})` : 'none'}
          stroke={shade(color, -40)}
          strokeWidth={shape.strokeTop && i === 0 ? 7 : 2.5}
          strokeLinecap="round"
          opacity="0.75"
        />
      ))}
    </svg>
  );
}
