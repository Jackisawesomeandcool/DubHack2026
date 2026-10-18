import { useSyncExternalStore } from 'react';

// The "AI-powered fits" switch in the search bar. On: Gemini picks the best matches (smarter on vague
// prompts, slower). Off: instant keyword search. The choice is remembered in this browser; the switch only
// shows when the server reports an AI provider (GET /api/health -> ai).
const KEY = 'haul.ai';
const listeners = new Set();

function read() {
  try {
    return localStorage.getItem(KEY) !== '0'; // default: on
  } catch {
    return true;
  }
}

let state = { enabled: read(), available: false };

function set(patch) {
  state = { ...state, ...patch };
  listeners.forEach((l) => l());
}

export const aiEnabled = () => state.enabled; // sent with every search

export function setAiEnabled(enabled) {
  try { localStorage.setItem(KEY, enabled ? '1' : '0'); } catch { /* private mode */ }
  set({ enabled });
}

export function setAiAvailable(available) {
  if (available !== state.available) set({ available });
}

export function useAiMode() {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => state,
  );
}
