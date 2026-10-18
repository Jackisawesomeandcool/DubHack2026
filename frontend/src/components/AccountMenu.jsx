import { useEffect, useRef, useState } from 'react';
import { go, isGuest, loadUser, logOut } from '../lib/session.js';

// Compact profile button at the far right of the header. Clicking it opens a
// small menu with who's signed in and the way out (or in, for guests).
export default function AccountMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const user = loadUser();

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    const onKey = (e) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('pointerdown', onDown); window.removeEventListener('keydown', onKey); };
  }, [open]);

  if (!user && !isGuest()) return null;
  const name = user ? user.firstName || user.username || 'You' : 'Guest';

  return (
    <div className="account" ref={ref}>
      <button
        type="button"
        className={`account__btn${open ? ' is-open' : ''}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account: ${name}`}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="account__avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>
        <span className="account__name">{name}</span>
        <svg className="account__chev" viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
          <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="account__menu" role="menu">
          <div className="account__who">
            <strong>{user ? name : 'Browsing as guest'}</strong>
            {user?.username && <span>@{user.username}</span>}
            {user?.email && <span>{user.email}</span>}
          </div>
          {user ? (
            <button type="button" role="menuitem" className="account__item" onClick={() => logOut().then(() => go('/login'))}>
              Log out
            </button>
          ) : (
            <>
              <button type="button" role="menuitem" className="account__item" onClick={() => logOut().then(() => go('/signup'))}>
                Create an account
              </button>
              <button type="button" role="menuitem" className="account__item" onClick={() => logOut().then(() => go('/login'))}>
                Log in
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
