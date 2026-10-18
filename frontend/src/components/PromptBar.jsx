import { useEffect, useRef, useState } from 'react';

// Floating finder at the bottom. Submit -> options appear above it.
export default function PromptBar({ onSubmit, busy }) {
  const [value, setValue] = useState('');
  // While the user types, the box holds still (CSS drops its twinkle); it resumes once they pause.
  const [typing, setTyping] = useState(false);
  const idle = useRef(null);

  function stopTyping() {
    clearTimeout(idle.current);
    setTyping(false);
  }
  function onType(e) {
    setValue(e.target.value);
    setTyping(true);
    clearTimeout(idle.current);
    idle.current = setTimeout(() => setTyping(false), 1200);
  }
  useEffect(() => () => clearTimeout(idle.current), []);

  function submit(e) {
    e.preventDefault();
    const prompt = value.trim();
    if (!prompt || busy) return;
    onSubmit(prompt);
    setValue('');
    stopTyping();
  }

  return (
    <form className={`prompt${busy ? ' is-busy' : ''}${typing ? ' is-typing' : ''}`} onSubmit={submit}>
      <input
        className="prompt__input"
        type="text"
        value={value}
        maxLength={400}
        placeholder="Find a piece to swap in… try “more 90s, under $150”"
        aria-label="Find a piece to swap in"
        onChange={onType}
        onBlur={stopTyping}
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
