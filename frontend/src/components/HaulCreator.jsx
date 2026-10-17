import { useEffect, useMemo, useRef, useState } from 'react';
import FitSelector from './FitSelector.jsx';
import HaulTotal from './HaulTotal.jsx';
import ShareControl from './ShareControl.jsx';
import FashionCanvas from './FashionCanvas.jsx';
import OptionsTray from './OptionsTray.jsx';
import SearchHistory from './SearchHistory.jsx';
import PromptBar from './PromptBar.jsx';
import { randomFit, suggest } from '../lib/api.js';
import { MAX_FITS, MAX_ITEMS, addItem, emptyFit, fitTotal, moveItem, onBoard, removeItem, swapItem, withPositions } from '../lib/haul.js';

const MAX_HISTORY = 6;

export default function HaulCreator() {
  const [fits, setFits] = useState([emptyFit()]);
  const [current, setCurrent] = useState(0);
  const [loadingFit, setLoadingFit] = useState(false);
  const [fitError, setFitError] = useState('');
  const [selected, setSelected] = useState(null); // piece selected on the board

  // Search history: each entry keeps its prompt and the options it returned.
  const [history, setHistory] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const nextId = useRef(1);
  const booted = useRef(false);

  const fit = fits[current];
  const total = useMemo(() => fitTotal(fit), [fit]);
  const hasAnyItems = fits.some((f) => f.items.length);
  const active = history.find((h) => h.id === activeId) || null;

  const update = (index, fn) => setFits((prev) => prev.map((f, i) => (i === index ? fn(f) : f)));
  const patchHistory = (id, patch) => setHistory((prev) => prev.map((h) => (h.id === id ? { ...h, ...patch } : h)));

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
    const id = nextId.current++;
    setHistory((prev) => [{ id, prompt, options: [], loading: true, error: '' }, ...prev].slice(0, MAX_HISTORY));
    setActiveId(id);
    try {
      const { items } = await suggest(prompt, null, fit.items.map((i) => i.name));
      patchHistory(id, { options: items, loading: false });
    } catch {
      patchHistory(id, { loading: false, error: 'couldn’t find that — try again' });
    }
  }

  function addFit() {
    if (fits.length >= MAX_FITS) return;
    const index = fits.length;
    setFits((prev) => [...prev, emptyFit()]);
    setCurrent(index);
    loadRandom(index);
  }

  return (
    <main className="app">
      <header className="bar">
        <FitSelector fits={fits} current={current} onSelect={setCurrent} onAdd={loadingFit ? undefined : addFit} />
        <div className="bar__right">
          <HaulTotal total={total} />
          <ShareControl fits={fits} current={current} disabled={!hasAnyItems || loadingFit} />
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
        onSelectionChange={setSelected}
      />

      <SearchHistory entries={history} activeId={activeId} onSelect={setActiveId} />

      <footer className="dock">
        {active && (
          <OptionsTray
            options={active.options}
            loading={active.loading}
            error={active.error}
            isOnBoard={(item) => onBoard(fit, item)}
            full={fit.items.length >= MAX_ITEMS}
            swapMode={Boolean(selected)}
            onSwap={(item) => { if (selected) update(current, (f) => swapItem(f, selected, item)); }}
            onAdd={(item) => update(current, (f) => addItem(f, item))}
            onDismiss={() => setActiveId(null)}
          />
        )}
        <PromptBar onSubmit={find} busy={Boolean(active?.loading)} />
      </footer>
    </main>
  );
}
