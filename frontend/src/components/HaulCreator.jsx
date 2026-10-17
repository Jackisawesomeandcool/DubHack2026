import { useEffect, useMemo, useRef, useState } from 'react';
import FitSelector from './FitSelector.jsx';
import HaulTotal from './HaulTotal.jsx';
import ShareControl from './ShareControl.jsx';
import FashionCanvas from './FashionCanvas.jsx';
import OptionsTray from './OptionsTray.jsx';
import SearchHistory from './SearchHistory.jsx';
import PromptBar from './PromptBar.jsx';
import ModelsToggle from './ModelsToggle.jsx';
import { health, randomFit, seen, suggest } from '../lib/api.js';
import { MAX_FITS, MAX_ITEMS, addItem, emptyFit, fitTotal, moveItem, onBoard, removeItem, sameProduct, swapItem, withPositions } from '../lib/haul.js';

const MAX_HISTORY = 7;

export default function HaulCreator() {
  const [fits, setFits] = useState([emptyFit()]);
  const [current, setCurrent] = useState(0);
  const [loadingFit, setLoadingFit] = useState(false);
  const [fitError, setFitError] = useState('');

  // Search history: each entry keeps its prompt and the options it returned.
  const [history, setHistory] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const nextId = useRef(1);
  const booted = useRef(false);

  // Swap session for the selected piece: alternatives are previewed on the
  // board and only kept when the user says so.
  const [models, setModels] = useState(() => { try { return localStorage.getItem('haul:models') === '1'; } catch { return false; } });
  const modelsRef = useRef(models);
  modelsRef.current = models;
  const [setup, setSetup] = useState(null); // backend readiness notice
  const [dragOut, setDragOut] = useState(null); // piece currently held outside the board
  const [swap, setSwap] = useState(null); // { uid, original, alts, index, loading, error }
  const swapRef = useRef(null);
  swapRef.current = swap;

  const fit = fits[current];
  const total = useMemo(() => fitTotal(fit), [fit]);
  const hasAnyItems = fits.some((f) => f.items.length);
  const active = history.find((h) => h.id === activeId) || null;
  const selectedItem = swap ? fit.items.find((i) => i.uid === swap.uid) || null : null;

  const update = (index, fn) => setFits((prev) => prev.map((f, i) => (i === index ? fn(f) : f)));
  const patchHistory = (id, patch) => setHistory((prev) => prev.map((h) => (h.id === id ? { ...h, ...patch } : h)));

  // Every fit starts as a random real fit.
  async function loadRandom(index) {
    setLoadingFit(true);
    setFitError('');
    try {
      const { items } = await randomFit(modelsRef.current);
      update(index, () => ({ items: withPositions(items) }));
      seen(items);
    } catch (err) {
      setFitError(`couldn’t load a haul — ${err.message || 'try again'}`);
    } finally {
      setLoadingFit(false);
    }
  }

  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    loadRandom(0);
    // Until background removal is ready on the backend, say so.
    let timer;
    const check = async () => {
      try {
        const h = await health();
        if (!h.key) setSetup('backend has no XAI_API_KEY — add it to backend/.env');
        else if (!h.cutouts) { setSetup('preparing cutouts (installing background removal)…'); timer = setTimeout(check, 4000); }
        else setSetup(null);
      } catch { setSetup('backend not running — start python3 server.py'); timer = setTimeout(check, 4000); }
    };
    check();
    return () => clearTimeout(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Click the error message to try loading again.
  const retry = () => !loadingFit && fit.items.length === 0 && loadRandom(current);

  async function find(prompt) {
    const id = nextId.current++;
    setHistory((prev) => [{ id, prompt, options: [], loading: true, error: '' }, ...prev].slice(0, MAX_HISTORY));
    setActiveId(id);
    try {
      const items = await suggest(prompt, null, fit.items.map((i) => i.name), (partial) =>
        patchHistory(id, { options: partial, loading: false }), modelsRef.current);
      patchHistory(id, { options: items, loading: false });
    } catch {
      patchHistory(id, { loading: false, error: 'couldn’t find that — try again' });
    }
  }

  // ---- swap session ------------------------------------------------------
  function revertSwap(s) {
    if (s && s.index !== -1) {
      update(current, (f) => {
        const cur = f.items.find((i) => i.uid === s.uid);
        return cur ? swapItem(f, cur, s.original) : f;
      });
    }
  }

  async function beginSwap(item) {
    revertSwap(swapRef.current);
    const session = { uid: item.uid, original: item, alts: [], index: -1, loading: true, error: '' };
    setSwap(session);
    setActiveId(null);
    try {
      const prompt = `${item.category === 'bottom' ? 'pants' : item.category} similar in style to ${item.name}`;
      const apply = (list) => {
        const alts = list.filter((a) => !sameProduct(a, item));
        setSwap((s) => (s && s.uid === item.uid ? { ...s, alts, loading: false } : s));
      };
      apply(await suggest(prompt, item.category, fit.items.map((i) => i.name), apply, modelsRef.current));
    } catch {
      setSwap((s) => (s && s.uid === item.uid ? { ...s, loading: false, error: 'couldn’t find alternatives' } : s));
    }
  }

  function onSelectionChange(item) {
    const s = swapRef.current;
    if (item) {
      if (!s || s.uid !== item.uid) beginSwap(item);
      return;
    }
    // Deselected without keeping: changes they didn't confirm are dropped.
    if (s) { revertSwap(s); setSwap(null); }
  }

  function previewAt(index) {
    setSwap((s) => {
      if (!s) return s;
      const target = index === -1 ? s.original : s.alts[index];
      if (!target) return s;
      update(current, (f) => {
        const cur = f.items.find((i) => i.uid === s.uid);
        return cur ? swapItem(f, cur, target) : f;
      });
      return { ...s, index };
    });
  }

  function previewOption(item) {
    setSwap((s) => {
      if (!s) return s;
      let alts = s.alts;
      let index = alts.findIndex((a) => sameProduct(a, item));
      if (index === -1) { alts = [item, ...alts]; index = 0; }
      update(current, (f) => {
        const cur = f.items.find((i) => i.uid === s.uid);
        return cur ? swapItem(f, cur, item) : f;
      });
      return { ...s, alts, index };
    });
  }

  const readyAlts = swap ? swap.alts.filter((a) => !a.pending) : [];
  const swapUi = swap && {
    dirty: swap.index !== -1,
    canPrev: readyAlts.length > 0,
    canNext: readyAlts.length > 0,
    loading: swap.loading,
    onPrev: () => previewAt(swap.index <= -1 ? swap.alts.length - 1 : swap.index - 1),
    onNext: () => previewAt(swap.index >= swap.alts.length - 1 ? -1 : swap.index + 1),
    onKeep: () => { if (selectedItem) seen([selectedItem]); setSwap((s) => (s ? { ...s, original: selectedItem, index: -1 } : s)); },
    onUndo: () => previewAt(-1),
  };

  function deleteFit(index) {
    if (fits.length <= 1) return;
    revertSwap(swapRef.current);
    setSwap(null);
    setFits((prev) => prev.filter((_, i) => i !== index));
    setCurrent((cur) => (cur > index ? cur - 1 : Math.min(cur, fits.length - 2)));
  }

  function addFit() {
    if (fits.length >= MAX_FITS) return;
    const index = fits.length;
    setFits((prev) => [...prev, emptyFit()]);
    setCurrent(index);
    setSwap(null);
    loadRandom(index);
  }

  const trayOptions = active ? active.options : swap ? swap.alts : [];
  const trayLoading = active ? active.loading : Boolean(swap?.loading);
  const trayError = active ? active.error : swap?.error || '';
  const showTray = Boolean(active) || Boolean(swap);

  return (
    <main className="app">
      <header className="bar">
        <FitSelector fits={fits} current={current} onSelect={(i) => { revertSwap(swapRef.current); setSwap(null); setCurrent(i); }} onAdd={loadingFit ? undefined : addFit} onDelete={loadingFit ? undefined : deleteFit} />
        <div className="bar__right">
          <HaulTotal total={total} pendingTotal={dragOut ? total - (Number(dragOut.price) || 0) : null} />
          <ShareControl fits={fits} current={current} disabled={!hasAnyItems || loadingFit} />
        </div>
      </header>

      <FashionCanvas
        items={fit.items}
        fitKey={current}
        editable
        loading={loadingFit}
        hint={fitError}
        onHintClick={retry}
        swapUi={swapUi}
        onMove={(item, x, y) => update(current, (f) => moveItem(f, item, x, y))}
        onRemove={(item) => { if (swap?.uid === item.uid) setSwap(null); update(current, (f) => removeItem(f, item)); }}
        onSelectionChange={onSelectionChange}
        onDragOutChange={setDragOut}
      />

      <SearchHistory entries={history} activeId={activeId} onSelect={setActiveId} />

      <footer className="dock">
        {setup && <div className="notice">{setup}</div>}
        {showTray && (
          <OptionsTray
            title={swap && !active ? `swap ${swap.original.category === 'bottom' ? 'bottoms' : swap.original.category}` : ''}
            options={trayOptions}
            loading={trayLoading}
            error={trayError}
            isOnBoard={(item) => onBoard(fit, item)}
            previewing={swap ? selectedItem : null}
            full={fit.items.length >= MAX_ITEMS}
            swapMode={Boolean(swap)}
            onSwap={previewOption}
            onAdd={(item) => { seen([item]); update(current, (f) => addItem(f, item)); }}
            onDismiss={() => { if (active) setActiveId(null); else { revertSwap(swapRef.current); setSwap(null); } }}
          />
        )}
        <div className="dock__row">
          <PromptBar onSubmit={find} busy={Boolean(active?.loading)} />
          <ModelsToggle value={models} onChange={(v) => { setModels(v); try { localStorage.setItem('haul:models', v ? '1' : '0'); } catch {} }} />
        </div>
      </footer>
    </main>
  );
}
