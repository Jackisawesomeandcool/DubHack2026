import { useState } from 'react';

// Floating prompt control at the bottom. Submit -> the current fit updates.
export default function PromptBar({ onSubmit, busy }) {
  const [value, setValue] = useState('');

  function submit(e) {
    e.preventDefault();
    const prompt = value.trim();
    if (!prompt || busy) return;
    onSubmit(prompt);
    setValue('');
  }

  return (
    <form className={`prompt${busy ? ' is-busy' : ''}`} onSubmit={submit}>
      <input
        className="prompt__input"
        type="text"
        value={value}
        maxLength={400}
        placeholder="describe your next fit..."
        aria-label="Describe your next fit"
        onChange={(e) => setValue(e.target.value)}
        disabled={busy}
      />
      <button
        type="submit"
        className="prompt__send"
        aria-label="Create fit"
        disabled={busy || !value.trim()}
      >
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
          <path d="M10 16V4M4.5 9.5 10 4l5.5 5.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </form>
  );
}
