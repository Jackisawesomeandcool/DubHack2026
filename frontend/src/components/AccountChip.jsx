import { go, isGuest, loadUser, logOut } from '../lib/session.js';

// Top-left of the builder: who's here, and the way out (or in).
export default function AccountChip() {
  const user = loadUser();
  if (!user && !isGuest()) return null;
  const name = user ? user.firstName || user.username || 'You' : 'Guest';
  return (
    <div className="account">
      <span className="account__avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>
      <span className="account__name" title={user?.username ? `@${user.username}` : undefined}>{name}</span>
      {user ? (
        <button type="button" className="account__link" onClick={() => { logOut(); go('/login'); }}>Log out</button>
      ) : (
        <a className="account__link" href="/signup">Sign up</a>
      )}
    </div>
  );
}
