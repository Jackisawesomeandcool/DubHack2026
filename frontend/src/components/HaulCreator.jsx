import { useEffect, useMemo, useRef, useState } from 'react';
import FitSelector from './FitSelector.jsx';
import HaulTotal from './HaulTotal.jsx';
import ShareControl from './ShareControl.jsx';
import FashionCanvas from './FashionCanvas.jsx';
import OptionsTray from './OptionsTray.jsx';
import PromptBar from './PromptBar.jsx';
import { randomFit, suggest } from '../lib/api.js';
import { MAX_FITS, emptyFit, fitTotal, itemKey, moveItem, placeItem, removeItem, withPositions } from '../lib/haul.js';

export default function HaulCreator() {
  const [fits, setFits] = useState([emptyFit()]);
  const [current, setCurrent] = useState(0);
  const [loadingFit, setLoadingFit] = useState(false);
  const [fitError, setFitError] = useState('');

  const [options, setOptions] = useState([]);
  const [finding, setFinding] = useState(false);
  const [findError, setFindError] = useState('');
  const booted = useRef(false);

  const fit = fits[current];
  const total = useMemo(() => fitTotal(fit), [fit]);
  const boardKeys = useMemo(() => new Set(fit.items.map(itemKey)), [fit]);
  const hasAnyItems = fits.some((f) => f.items.length);

  const update = (index, fn) => setFits((prev) => prev.map((f, i) => (i === index ? fn(f) : f)));

  // Every fit starts as a random real fit.
  async function loadRandom(index) {
    setLoadingFit(true);
    setFitError('');
    try {
      const { items } = await randomFit();
      update(index, () => ({ items: withPositions(items) }));
    } catch {
      setFitError('couldn’t load a fit — try again');
    } finally {
      setLoadingFit(false);
    }
  }

  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    loadRandom(0);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function find(prompt) {
    setFinding(true);
    setFindError('');
    try {
      const { items } = await suggest(prompt, null, fit.items.map((i) => i.name));
      setOptions(items);
    } catch {
      setOptions([]);
      setFindError('couldn’t find that — try again');
    } finally {
      setFinding(false);
    }
  }

  function addFit() {
    if (fits.length >= MAX_FITS) return;
    const index = fits.length;
    setFits((prev) => [...prev, emptyFit()]);
    setCurrent(index);
    setOptions([]);
    loadRandom(index);
  }

  return (
    <main className="app">
      <header className="bar">
        <FitSelector fits={fits} current={current} onSelect={(i) => { setCurrent(i); setOptions([]); }} onAdd={loadingFit ? undefined : addFit} />
        <div className="bar__right">
          <HaulTotal total={total} />
          <ShareControl fits={fits} disabled={!hasAnyItems || loadingFit} />
        </div>
      </header>

      <FashionCanvas
        items={fit.items}
        fitKey={current}
        editable
        loading={loadingFit}
        hint={fitError}
        onMove={(item, x, y) => update(current, (f) => moveItem(f, item, x, y))}
        onRemove={(item) => update(current, (f) => removeItem(f, item))}
      />

      <footer className="dock">
        <OptionsTray
          options={options}
          loading={finding}
          error={findError}
          boardKeys={boardKeys}
          onPick={(item) => update(current, (f) => placeItem(f, item))}
          onDismiss={() => { setOptions([]); setFindError(''); }}
        />
        <PromptBar onSubmit={find} busy={finding} />
      </footer>
    </main>
  );
}
