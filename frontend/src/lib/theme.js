import { useSyncExternalStore } from 'react';

// Color themes. The palettes themselves live in styles.css ([data-theme="..."] blocks);
// this file only knows the ids, remembers the choice, and puts it on <html>.
export const THEMES = [
  { id: 'studio', name: 'Studio', note: 'Warm grey, the original' },
  { id: 'midnight', name: 'Midnight', note: 'Dark, easy at night' },
  { id: 'maroon', name: 'Maroon', note: 'Deep red, dark' },
  { id: 'blush', name: 'Blush', note: 'Soft rose' },
  { id: 'sky', name: 'Sky', note: 'Cool blue' },
  { id: 'sage', name: 'Sage', note: 'Muted green' },
];

const KEY = 'haul.theme';
const DEFAULT = 'studio';
const listeners = new Set();
let current = DEFAULT;

const valid = (id) => THEMES.some((t) => t.id === id);

function read() {
  try {
    const id = localStorage.getItem(KEY);
    return valid(id) ? id : DEFAULT;
  } catch {
    return DEFAULT;
  }
}

function apply(id) {
  const root = document.documentElement;
  root.dataset.theme = id;
  // phone browser chrome follows the page color
  const bg = getComputedStyle(root).getPropertyValue('--bg').trim();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta && bg) meta.setAttribute('content', bg);
}

export function initTheme() {
  current = read();
  apply(current);
  // another tab changed it
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) { current = read(); apply(current); listeners.forEach((l) => l()); }
  });
}

export function setTheme(id) {
  if (!valid(id) || id === current) return;
  const root = document.documentElement;
  const calm = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (!calm) {
    // let the colors fade for a moment, then drop the class so it can't slow other animations
    root.classList.add('theme-switching');
    clearTimeout(setTheme.t);
    setTheme.t = setTimeout(() => root.classList.remove('theme-switching'), 450);
  }
  current = id;
  apply(id);
  try { localStorage.setItem(KEY, id); } catch { /* private mode: still works for this visit */ }
  listeners.forEach((l) => l());
}

const subscribe = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };
export const useTheme = () => useSyncExternalStore(subscribe, () => current, () => DEFAULT);
