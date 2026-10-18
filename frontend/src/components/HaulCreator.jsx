import { useEffect, useMemo, useRef, useState } from 'react';
import FitSelector from './FitSelector.jsx';
import HaulTotal from './HaulTotal.jsx';
import ShareControl from './ShareControl.jsx';
import FashionCanvas from './FashionCanvas.jsx';
import OptionsTray from './OptionsTray.jsx';
import SearchHistory from './SearchHistory.jsx';
import PromptBar from './PromptBar.jsx';
import Backdrop from './Backdrop.jsx';
import { health, randomFit, seen, suggest } from '../lib/api.js';
import { MAX_FITS, MAX_ITEMS, addItem, emptyFit, fitTotal, moveItem, onBoard, removeItem, sameProduct, swapItem, withPositions } from '../lib/haul.js';
import { isFavorite, loadFavorites, saveFavorites, toggleFavorite } from '../lib/favorites.js';

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

  // Product-only cutouts everywhere (no on-model shots).
  const modelsRef = useRef(false);
  try { localStorage.removeItem('haul:models'); } catch {}
  const [setup, setSetup] = useState(null); // backend readiness notice
  const [dragOut, setDragOut] = useState(null); // piece currently held outside the board

  // Starred listings (this browser) and whether the tray shows them instead of suggestions.
  const [favorites, setFavorites] = useState(loadFavorites);
  const [favMode, setFavMode] = useState(false);
  const favoritesRef = useRef(favorites);
  favoritesRef.current = favorites;
  // Everything starred, as is: no category filter, nothing hidden.
  const favoritesFor = (item) => favorites.filter((f) => !item || !sameProduct(f, item));
  function toggleFav(item) {
    const next = toggleFavorite(favoritesRef.current, item);
    setFavorites(next);
    saveFavorites(next);
  }

  // Swap session for the selected piece: alternatives are previewed on the
  // board and only kept when the user says so. `found` keeps the search
  // results while the tray is switched to favorites.
  const [swap, setSwap] = useState(null); // { uid, original, alts, found, index, loading, error }
  const swapRef = useRef(null);
  swapRef.current = swap;

  const fit = fits[current];
  const total = useMemo(() => fitTotal(fit), [fit]);
  const hasAnyItems = fits.some((f) => f.items.length);
  const active = history.find((h) => h.id === activeId) || null;
  const selectedItem = swap ? fit.items.find((i) => i.uid === swap.uid) || null : null;

  const update = (index, fn) => setFits((prev) => prev.map((f, i) => (i === index ? fn(f) : f)));
  const patchHistory = (id, patch) => setHistory((prev) => prev.map((h) => (h.id === id ? { ...h, ...patch } : h)));

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
    let timer;
    const check = async () => {
      try {
        const h = await health();
        if (!h.cutouts) { setSetup('preparing cutouts…'); timer = setTimeout(check, 4000); }
        else setSetup(null);
      } catch { setSetup('backend not running — start python server.py'); timer = setTimeout(check, 4000); }
    };
    check();
    return () => clearTimeout(timer);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Click the error message to try loading again.
  const retry = () => !loadingFit && fit.items.length === 0 && loadRandom(current);

  // Running a search (the arrow button / Enter) brings the tray back to suggestions.
  async function find(prompt) {
    if (favMode) toggleFavMode();
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
    const favs = favoritesFor(item);
    const session = { uid: item.uid, original: item, alts: favMode ? favs : [], found: [], index: -1, loading: !favMode, error: '' };
    setSwap(session);
    setActiveId(null);
    try {
      const prompt = `${item.category === 'bottom' ? 'pants' : item.category} similar in style to ${item.name}`;
      const apply = (list) => {
        const found = list.filter((a) => !sameProduct(a, item) && !fit.items.some((b) => b.uid !== item.uid && sameProduct(b, a)));
        setSwap((s) => (s && s.uid === item.uid ? { ...s, found, alts: favMode ? s.alts : found, loading: false } : s));
      };
      apply(await suggest(prompt, item.category, fit.items.map((i) => i.name), apply, modelsRef.current));
    } catch {
      setSwap((s) => (s && s.uid === item.uid ? { ...s, loading: false, error: favMode ? '' : 'couldn’t find alternatives' } : s));
    }
  }

  // Tray switch: suggestions <-> favorites. In a swap session the arrows then
  // cycle whichever list is showing; an unkept preview is dropped first.
  function toggleFavMode() {
    const next = !favMode;
    setFavMode(next);
    const s = swapRef.current;
    if (s) {
      revertSwap(s);
      setSwap({ ...s, alts: next ? favoritesFor(s.original) : s.found, index: -1, error: next ? '' : s.error });
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

  // Keyboard: ← → cycle alternatives for the selected piece, Enter keeps, Esc undoes.
  useEffect(() => {
    if (!swapUi) return undefined;
    const onKey = (e) => {
      if (e.target.closest?.('input, textarea')) return;
      if (e.key === 'ArrowLeft' && swapUi.canPrev) { e.preventDefault(); swapUi.onPrev(); }
      else if (e.key === 'ArrowRight' && swapUi.canNext) { e.preventDefault(); swapUi.onNext(); }
      else if (e.key === 'Enter' && swapUi.dirty) { e.preventDefault(); swapUi.onKeep(); }
      else if (e.key === 'Escape' && swapUi.dirty) { e.preventDefault(); swapUi.onUndo(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

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

  const trayOptions = swap ? swap.alts : favMode ? favoritesFor(null) : active ? active.options : [];
  const trayLoading = swap ? Boolean(swap.loading) && !favMode : favMode ? false : Boolean(active?.loading);
  const trayError = swap ? swap.error || '' : favMode ? '' : active?.error || '';
  const showTray = Boolean(active) || Boolean(swap) || favMode;

  return (
    <main className="app">
      <Backdrop index={current} />
      <header className="bar">
        <div className="bar__right">
          <HaulTotal total={total} resetKey={`${current}:${loadingFit}`} pendingTotal={dragOut ? total - (Number(dragOut.price) || 0) : null} />
          <ShareControl fits={fits} current={current} disabled={!hasAnyItems || loadingFit} />
        </div>
      </header>

      <div className="stage">
        <FitSelector
          fits={fits}
          current={current}
          onSelect={(i) => { revertSwap(swapRef.current); setSwap(null); setCurrent(i); }}
          onAdd={loadingFit ? undefined : addFit}
          onDelete={loadingFit ? undefined : deleteFit}
        />
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
          isFavorite={(item) => isFavorite(favorites, item)}
          onFavorite={toggleFav}
        />
      </div>

      <SearchHistory entries={history} activeId={activeId} onSelect={setActiveId} />

      <footer className="dock">
        {setup && <div className="notice">{setup}</div>}
        {showTray && (
          <OptionsTray
            title={swap ? `swap ${swap.original.category === 'bottom' ? 'bottoms' : swap.original.category}${favMode ? ' · favorites' : ''}` : favMode ? 'favorites' : ''}
            options={trayOptions}
            loading={trayLoading}
            error={trayError}
            isOnBoard={(item) => onBoard(fit, item)}
            previewing={swap ? selectedItem : null}
            full={fit.items.length >= MAX_ITEMS}
            swapMode={Boolean(swap)}
            onSwap={previewOption}
            onAdd={(item) => { seen([item]); update(current, (f) => addItem(f, item)); }}
            onDismiss={() => { if (favMode) setFavMode(false); else if (active) setActiveId(null); else { revertSwap(swapRef.current); setSwap(null); } }}
            favMode={favMode}
            favCount={favorites.length}
            onToggleFavMode={toggleFavMode}
          />
        )}
        <PromptBar onSubmit={find} busy={Boolean(active?.loading)} />
      </footer>
    </main>
  );
}
