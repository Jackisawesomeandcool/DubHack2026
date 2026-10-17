import { useEffect, useRef, useState } from 'react';
import { createShare } from '../lib/api.js';

// SHARE -> creates a link to the haul and copies it. Nothing more.
export default function ShareControl({ fits, disabled }) {
  const [state, setState] = useState('idle'); // idle | busy | copied | link | error
  const [link, setLink] = useState('');
  const timer = useRef(null);

  useEffect(() => () => clearTimeout(timer.current), []);

  async function share() {
    if (state === 'busy') return;
    setState('busy');
    try {
      const { id } = await createShare(fits.filter((f) => f.items.length));
      const url = `${window.location.origin}/h/${id}`;
      setLink(url);
      try {
        await navigator.clipboard.writeText(url);
        setState('copied');
      } catch {
        setState('link'); // clipboard blocked: show the link so it can be copied by hand
      }
    } catch {
      setState('error');
    }
    timer.current = setTimeout(() => setState('idle'), 2600);
  }

  const label = { idle: 'SHARE', busy: '…', copied: 'LINK COPIED', link: 'LINK READY', error: 'TRY AGAIN' }[state];

  return (
    <div className="share">
      <button
        type="button"
        className={`share__btn${state === 'copied' ? ' is-done' : ''}`}
        onClick={share}
        disabled={disabled || state === 'busy'}
      >
        {label}
      </button>
      {state === 'link' && (
        <input className="share__link" readOnly value={link} onFocus={(e) => e.target.select()} />
      )}
    </div>
  );
}
