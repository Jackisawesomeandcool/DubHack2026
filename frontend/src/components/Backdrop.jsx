import { useEffect, useState } from 'react';

// Moving background and the palette switcher.
// Each fit has its own palette (index % PALETTES). When the fit changes, a thick black
// jagged band sweeps across the screen and the palette swaps while it covers everything.
const PALETTES = 5;
const WIPE_MS = 900;
const SWAP_AT = WIPE_MS / 2;

export default function Backdrop({ index = 0 }) {
  const [shown, setShown] = useState(index); // fit whose palette/number is on screen
  const [wipe, setWipe] = useState(0);       // bump to (re)start the wipe

  useEffect(() => {
    document.documentElement.dataset.palette = String(shown % PALETTES);
  }, [shown]);

  useEffect(() => {
    if (index === shown) return undefined;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setShown(index);
      return undefined;
    }
    setWipe((w) => w + 1);
    const t = setTimeout(() => setShown(index), SWAP_AT);
    return () => clearTimeout(t);
  }, [index, shown]);

  return (
    <>
      <div className="backdrop" aria-hidden="true" />
      {wipe > 0 && (
        <div className="wipe" key={wipe} aria-hidden="true">
          <div className="wipe__band wipe__band--edge" />
          <div className="wipe__band" />
        </div>
      )}
    </>
  );
}
