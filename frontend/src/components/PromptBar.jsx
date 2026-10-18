import { useEffect, useRef, useState } from 'react';
import { setAiEnabled, useAiMode } from '../lib/aiMode.js';

// Floating finder at the bottom. Submit -> options appear above it.
export default function PromptBar({ onSubmit, busy, notice, onShowClosest, onDismissNotice }) {
  const [value, setValue] = useState('');
  // While the user types, the box holds still (CSS drops its twinkle); it resumes once they pause.
  const [typing, setTyping] = useState(false);
  const idle = useRef(null);
  const ai = useAiMode();

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
    <>
    {notice && (
      <div className="prompt__notice" role="status">
        <span className="prompt__notice-text">{notice.reason}</span>
        {notice.closest?.length > 0 && (
          <button type="button" className="prompt__notice-go" onClick={onShowClosest}>
            Show {notice.closest.length === 1 ? 'it' : 'closest'}
          </button>
        )}
        <button type="button" className="prompt__notice-x" aria-label="Dismiss" onClick={onDismissNotice}>×</button>
      </div>
    )}
    <form className={`prompt${busy ? ' is-busy' : ''}${typing ? ' is-typing' : ''}`} onSubmit={submit}>
      <input
        className="prompt__input"
        type="text"
        value={value}
        maxLength={400}
        placeholder="Describe your dream fit…"
        aria-label="Describe your dream fit"
        onChange={onType}
        onBlur={stopTyping}
        disabled={busy}
      />
      {ai.available && (
        <button
          type="button"
          className="prompt__ai"
          aria-pressed={ai.enabled}
          title={ai.enabled
            ? 'AI-powered fits: Gemini picks the best matches (a little slower). Click for instant keyword search.'
            : 'Instant keyword search. Click to let AI pick the best matches.'}
          onClick={() => setAiEnabled(!ai.enabled)}
        >
          <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden="true">
            <path d="M10 2.5l1.7 4.6 4.6 1.7-4.6 1.7L10 15.1l-1.7-4.6L3.7 8.8l4.6-1.7z M16 13l.8 2.2 2.2.8-2.2.8L16 19l-.8-2.2-2.2-.8 2.2-.8z" fill="currentColor" />
          </svg>
          <span className="prompt__ai-long">AI-powered fits</span>
          <span className="prompt__ai-short">AI</span>
        </button>
      )}
      <button type="submit" className="prompt__send" aria-label="Find" disabled={busy || !value.trim()}>
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <path d="M10 16V4M4.5 9.5 10 4l5.5 5.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </form>
    </>
  );
}
