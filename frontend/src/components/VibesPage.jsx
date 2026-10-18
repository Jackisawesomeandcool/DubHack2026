import { useState } from 'react';
import { go, loadVibes, saveVibes } from '../lib/session.js';

const MIN = 3;

// Each vibe is also the search term sent to /api/suggest on the first visit,
// so keep names the finder understands.
const VIBES = [
  { name: 'Y2K', swatch: ['#e7a6c8', '#7f9cc0', '#d9d2c3'] },
  { name: 'Grunge', swatch: ['#4a4a4f', '#2e3d5c', '#8a6a4a'] },
  { name: 'Coastal', swatch: ['#a9c3de', '#d9cfb8', '#ffffff'] },
  { name: 'Streetwear', swatch: ['#c9b28a', '#1d1c1a', '#e6e3dc'] },
  { name: 'Old money', swatch: ['#e8e1d2', '#6e7a5f', '#2e3d5c'] },
  { name: 'Scenecore', swatch: ['#1d1c1a', '#c2405f', '#e7a6c8'] },
  { name: 'Minimal', swatch: ['#ffffff', '#1d1c1a', '#b8b3aa'] },
  { name: 'Cottagecore', swatch: ['#f1e4c8', '#9db08a', '#c9826f'] },
];

// Sign up, step 2: pick a few aesthetics to seed the first search.
export default function VibesPage() {
  const [picked, setPicked] = useState(loadVibes);
  const ready = picked.length >= MIN;

  const toggle = (name) =>
    setPicked((p) => (p.includes(name) ? p.filter((n) => n !== name) : [...p, name]));

  function finish(vibes) {
    saveVibes(vibes);
    go('/');
  }

  return (
    <main className="vibes">
      <header className="vibes__bar">
        <div className="auth__brand">Haul</div>
        <div className="vibes__right">
          <div className="auth__steps" aria-label="Step 2 of 2">
            <span className="is-on" aria-hidden="true" /><span className="is-on" aria-hidden="true" />
            <small>Step 2 of 2</small>
          </div>
          <button type="button" className="vibes__skip" onClick={() => finish([])}>Skip</button>
        </div>
      </header>

      <div className="auth__head">
        <h1>Pick a few vibes</h1>
        <p>We’ll use these for your first search. Pick {MIN} or more.</p>
      </div>

      <div className="vibes__grid">
        {VIBES.map((v) => {
          const on = picked.includes(v.name);
          return (
            <button
              key={v.name}
              type="button"
              className={`vibe${on ? ' is-on' : ''}`}
              aria-pressed={on}
              onClick={() => toggle(v.name)}
            >
              <span className="vibe__swatch" aria-hidden="true">
                {v.swatch.map((c) => <i key={c} style={{ background: c }} />)}
              </span>
              <span className="vibe__name">{v.name}</span>
              {on && (
                <span className="vibe__check" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="14" height="14"><path d="M5 12l5 5 9-10" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </span>
              )}
            </button>
          );
        })}
      </div>

      <footer className="vibes__footer">
        <span>
          <strong>{picked.length} selected</strong> · {ready ? 'add more if you like' : `pick ${MIN - picked.length} more`}
        </span>
        <button type="button" className="auth__submit" disabled={!ready} onClick={() => finish(picked)}>
          Start building
        </button>
      </footer>
    </main>
  );
}
