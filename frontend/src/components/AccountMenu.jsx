import { useEffect, useRef, useState } from 'react';
import { clearMyData, deleteAccount, go, isGuest, loadUser, logOut } from '../lib/session.js';

// Compact profile button at the far right of the header. Clicking it opens a
// small menu with who's signed in, the privacy controls, and the way out (or in, for guests).
// "Clear my data" and "Delete account" each ask for one more click before anything is removed.
export default function AccountMenu() {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(null); // null | 'clear' | 'delete'
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const ref = useRef(null);
  const user = loadUser();

  function close() { setOpen(false); setConfirm(null); setError(''); }

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (!ref.current?.contains(e.target)) close(); };
    const onKey = (e) => e.key === 'Escape' && close();
    window.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey);
    return () => { window.removeEventListener('pointerdown', onDown); window.removeEventListener('keydown', onKey); };
  }, [open]);

  if (!user && !isGuest()) return null;
  const name = user ? user.firstName || user.username || 'You' : 'Guest';

  async function run() {
    setBusy(true);
    setError('');
    try {
      if (confirm === 'delete') {
        await deleteAccount();
        go('/login');
      } else {
        await clearMyData();
        go('/');
      }
    } catch (err) {
      setError(err.message || 'Something went wrong — try again.');
      setBusy(false);
    }
  }

  const copy = {
    clear: {
      title: 'Clear my data?',
      body: user
        ? 'Removes your saved favorites, hauls and search history from your account and this browser. Your account stays.'
        : 'Removes the favorites saved in this browser.',
      go: 'Clear data',
    },
    delete: {
      title: 'Delete your account?',
      body: 'Permanently deletes your account, favorites, hauls and search history, and signs you out everywhere. Links you already shared stay viewable.',
      go: 'Delete account',
    },
  }[confirm];

  return (
    <div className="account" ref={ref}>
      <button
        type="button"
        className={`account__btn${open ? ' is-open' : ''}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account: ${name}`}
        onClick={() => (open ? close() : setOpen(true))}
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
          </div>

          {confirm ? (
            <div className="account__confirm" role="alertdialog" aria-label={copy.title}>
              <strong>{copy.title}</strong>
              <p>{copy.body}</p>
              {error && <p className="account__error" role="alert">{error}</p>}
              <div className="account__confirm-row">
                <button type="button" className="account__cancel" onClick={() => { setConfirm(null); setError(''); }} disabled={busy}>Cancel</button>
                <button type="button" className="account__danger" onClick={run} disabled={busy}>{busy ? '…' : copy.go}</button>
              </div>
            </div>
          ) : (
            <>
              {user ? (
                <>
                  <button type="button" role="menuitem" className="account__item" onClick={() => logOut().then(() => go('/login'))}>
                    Log out
                  </button>
                  <div className="account__sep" role="separator" />
                  <button type="button" role="menuitem" className="account__item" onClick={() => setConfirm('clear')}>
                    Clear my data
                  </button>
                  <button type="button" role="menuitem" className="account__item account__item--danger" onClick={() => setConfirm('delete')}>
                    Delete account
                  </button>
                </>
              ) : (
                <>
                  <button type="button" role="menuitem" className="account__item" onClick={() => logOut().then(() => go('/signup'))}>
                    Create an account
                  </button>
                  <button type="button" role="menuitem" className="account__item" onClick={() => logOut().then(() => go('/login'))}>
                    Log in
                  </button>
                  <div className="account__sep" role="separator" />
                  <button type="button" role="menuitem" className="account__item" onClick={() => setConfirm('clear')}>
                    Clear my data
                  </button>
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
