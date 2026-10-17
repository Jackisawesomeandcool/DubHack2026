import { useMemo, useState } from 'react';
import FitSelector from './FitSelector.jsx';
import HaulTotal from './HaulTotal.jsx';
import ShareControl from './ShareControl.jsx';
import FashionCanvas from './FashionCanvas.jsx';
import OptionsTray from './OptionsTray.jsx';
import PromptBar from './PromptBar.jsx';
import { suggest } from '../lib/api.js';
import { MAX_FITS, emptyFit, fitTotal, itemKey, placeItem, removeItem } from '../lib/haul.js';

export default function HaulCreator() {
  const [fits, setFits] = useState([emptyFit()]);
  const [current, setCurrent] = useState(0);
  const [focusCategory, setFocusCategory] = useState(null);

  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fit = fits[current];
  const total = useMemo(() => fitTotal(fit), [fit]);
  const boardKeys = useMemo(() => new Set(fit.items.map(itemKey)), [fit]);
  const hasAnyItems = fits.some((f) => f.items.length);

  async function find(prompt, category) {
    setLoading(true);
    setError('');
    try {
      const { items } = await suggest(prompt, category, fit.items.map((i) => i.name));
      setOptions(items);
    } catch {
      setOptions([]);
      setError('couldn’t find that — try again');
    } finally {
      setLoading(false);
    }
  }

  function pick(item) {
    setFits((prev) => prev.map((f, i) => (i === current ? placeItem(f, item) : f)));
    if (focusCategory === item.category) setFocusCategory(null);
  }

  function remove(item) {
    setFits((prev) => prev.map((f, i) => (i === current ? removeItem(f, item) : f)));
  }

  function addFit() {
    if (fits.length >= MAX_FITS) return;
    setFits((prev) => [...prev, emptyFit()]);
    setCurrent(fits.length);
    setFocusCategory(null);
  }

  return (
    <main className="app">
      <header className="bar">
        <FitSelector fits={fits} current={current} onSelect={(i) => { setCurrent(i); setFocusCategory(null); }} onAdd={addFit} />
        <div className="bar__right">
          <HaulTotal total={total} />
          <ShareControl fits={fits} disabled={!hasAnyItems} />
        </div>
      </header>

      <FashionCanvas
        items={fit.items}
        fitKey={current}
        editable
        focusCategory={focusCategory}
        onSlotClick={(cat) => setFocusCategory((cur) => (cur === cat ? null : cat))}
        onRemove={remove}
      />

      <footer className="dock">
        <OptionsTray
          options={options}
          loading={loading}
          error={error}
          boardKeys={boardKeys}
          onPick={pick}
          onDismiss={() => { setOptions([]); setError(''); }}
        />
        <PromptBar onSubmit={find} busy={loading} category={focusCategory} onClearCategory={() => setFocusCategory(null)} />
      </footer>
    </main>
  );
}
