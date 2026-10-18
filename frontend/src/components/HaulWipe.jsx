import { useLayoutEffect, useRef } from 'react';
import { placeFor } from '../lib/layout.js';

const DURATION = 680; // ms — long enough to notice, short enough to keep working
const THICKNESS = 18; // px — the black line
// Afterimage: a soft smear behind the line covering where it was TRAIL_LAG ms
// ago. Long at full speed, tucked under the line at the slow start and end.
const TRAIL_LAG = 55;

// Gradient angles (CSS: 0deg points up, clockwise). The line travels in this direction.
export const WIPE_DIRECTIONS = [
  135, // top-left -> bottom-right
  315, // bottom-right -> top-left
  90,  // left -> right
  270, // right -> left
  180, // top -> bottom
  0,   // bottom -> top
];

let last = -1;
export function randomDirection() {
  let i;
  do { i = Math.floor(Math.random() * WIPE_DIRECTIONS.length); } while (i === last && WIPE_DIRECTIONS.length > 1);
  last = i;
  return WIPE_DIRECTIONS[i];
}

const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

function setMask(el, value) {
  if (!el) return;
  el.style.maskImage = value;
  el.style.webkitMaskImage = value;
}

// Haul-switch transition. A black line sweeps across the board; behind it the
// new haul's pieces show (stageRef, the live board), ahead of it the old haul's
// pieces stay (drawn here as a static copy). Both are clipped with masks that
// meet exactly under the line.
export default function HaulWipe({ wipe, canvasRef, stageRef, onDone }) {
  const oldRef = useRef(null);
  const lineRef = useRef(null);
  const trailRef = useRef(null);

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const { width: W, height: H } = canvas.getBoundingClientRect();
    const deg = wipe.dir;
    const rad = (deg * Math.PI) / 180;
    const sin = Math.sin(rad), cos = Math.cos(rad);
    // Length of the CSS gradient line for this angle and box.
    const L = Math.abs(W * sin) + Math.abs(H * cos);
    const pad = (THICKNESS / 2 + 2) / L; // start and end with the line fully off the board
    const span = `${Math.hypot(W, H) + 40}px`;
    if (lineRef.current) { lineRef.current.style.width = span; lineRef.current.style.height = `${THICKNESS}px`; }
    if (trailRef.current) trailRef.current.style.width = span;
    const along = (t) => -pad + ease(Math.max(0, Math.min(1, t))) * (1 + 2 * pad); // 0..1 along the gradient line
    const place = (el, p) => {
      if (!el) return;
      const s = (p - 0.5) * L;
      el.style.transform = `translate(-50%, -50%) translate(${s * sin}px, ${-s * cos}px) rotate(${deg}deg)`;
    };
    // The smear runs from the line back to where the line was TRAIL_LAG ms ago.
    const smear = (pNow, pThen) => {
      const el = trailRef.current;
      if (!el) return;
      el.style.height = `${Math.max(0, (pNow - pThen) * L) + THICKNESS / 2}px`;
      place(el, (pNow + pThen) / 2 - THICKNESS / 4 / L);
    };

    function frame(ms) {
      const p = along(ms / DURATION);
      const pct = `${(p * 100).toFixed(3)}%`;
      setMask(stageRef.current, `linear-gradient(${deg}deg, #000 ${pct}, transparent ${pct})`);
      setMask(oldRef.current, `linear-gradient(${deg}deg, transparent ${pct}, #000 ${pct})`);
      place(lineRef.current, p);
      smear(p, along((ms - TRAIL_LAG) / DURATION));
    }

    frame(0); // before the first paint, so the new haul never flashes in
    const start = performance.now();
    const end = DURATION + TRAIL_LAG; // let the afterimage leave too
    let raf = requestAnimationFrame(function tick(now) {
      const ms = Math.min(end, now - start);
      frame(ms);
      if (ms < end) raf = requestAnimationFrame(tick);
      else { setMask(stageRef.current, ''); onDone(); }
    });
    return () => { cancelAnimationFrame(raf); setMask(stageRef.current, ''); };
  }, [wipe]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div ref={oldRef} className="canvas__stage canvas__stage--old" aria-hidden="true">
        {wipe.from.map((item, i) => (
          <div
            key={item.uid}
            className="item item--ghost"
            style={{ left: `${item.x}%`, top: `${item.y}%`, width: `calc(var(--u) * ${placeFor(item.category).w})`, zIndex: 10 + i }}
          >
            <span className="item__art"><img src={item.image} alt="" draggable="false" /></span>
          </div>
        ))}
      </div>
      <div className="wipe-trail" ref={trailRef} aria-hidden="true" />
      <div className="wipe-line" ref={lineRef} aria-hidden="true" />
    </>
  );
}
