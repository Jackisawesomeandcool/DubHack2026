import { useEffect, useMemo, useRef, useState } from 'react';
import FitSelector from './FitSelector.jsx';
import HaulTotal from './HaulTotal.jsx';
import ShareControl from './ShareControl.jsx';
import FashionCanvas from './FashionCanvas.jsx';
import PromptBar from './PromptBar.jsx';
import { curate } from '../lib/api.js';
import { MAX_FITS, emptyFit, fitTotal } from '../lib/haul.js';

const STARTER_PROMPT = 'late 2000s downtown outfit with baggy jeans and boots';

export default function HaulCreator() {
  const [fits, setFits] = useState([emptyFit()]);
  const [current, setCurrent] = useState(0);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const booted = useRef(false);

  const fit = fits[current];
  const total = useMemo(() => fitTotal(fit), [fit]);
  const hasAnyItems = fits.some((f) => f.items.length);

  async function generate(prompt, target = current) {
    setBusy(true);
    setFailed(false);
    try {
      const { items } = await curate(prompt);
      setFits((prev) => prev.map((f, i) => (i === target ? { items } : f)));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  // Open on a real composition instead of an empty surface.
  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    generate(STARTER_PROMPT, 0);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function addFit() {
    if (fits.length >= MAX_FITS) return;
    setFits((prev) => [...prev, emptyFit()]);
    setCurrent(fits.length);
  }

  return (
    <main className="app">
      <header className="bar">
        <FitSelector fits={fits} current={current} onSelect={setCurrent} onAdd={addFit} />
        <div className="bar__right">
          <HaulTotal total={total} />
          <ShareControl fits={fits} disabled={!hasAnyItems || busy} />
        </div>
      </header>

      <FashionCanvas
        items={fit.items}
        fitKey={current}
        busy={busy}
        emptyHint={failed ? 'couldn’t curate that one — try again' : 'describe a fit below to fill this one'}
      />

      <footer className="dock">
        <PromptBar onSubmit={(p) => generate(p)} busy={busy} />
      </footer>
    </main>
  );
}
