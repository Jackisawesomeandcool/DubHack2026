import { useEffect, useRef, useState } from 'react';
import { SLOT_LABEL } from '../lib/haul.js';

// Floating finder at the bottom. Submit -> options appear above it.
// An optional category (from clicking an empty slot) narrows the search.
export default function PromptBar({ onSubmit, busy, category, onClearCategory }) {
  const [value, setValue] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (category) inputRef.current?.focus();
  }, [category]);

  function submit(e) {
    e.preventDefault();
    const prompt = value.trim();
    if (!prompt || busy) return;
    onSubmit(prompt, category);
    setValue('');
  }

  const placeholder = category ? `find ${SLOT_LABEL[category]}...` : 'describe a piece or a vibe...';

  return (
    <form className={`prompt${busy ? ' is-busy' : ''}`} onSubmit={submit}>
      {category && (
        <button type="button" className="prompt__tag" onClick={onClearCategory} aria-label="Search all pieces">
          {SLOT_LABEL[category]} ×
        </button>
      )}
      <input
        ref={inputRef}
        className="prompt__input"
        type="text"
        value={value}
        maxLength={400}
        placeholder={placeholder}
        aria-label={placeholder}
        onChange={(e) => setValue(e.target.value)}
        disabled={busy}
      />
      <button type="submit" className="prompt__send" aria-label="Find" disabled={busy || !value.trim()}>
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <path d="M10 16V4M4.5 9.5 10 4l5.5 5.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </form>
  );
}
