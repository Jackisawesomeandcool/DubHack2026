import HaulCreator from './components/HaulCreator.jsx';
import GuestHaul from './components/GuestHaul.jsx';
import AuthPage from './components/AuthPage.jsx';
import { useEffect } from 'react';
import { hasSession, loadUser, refreshUser, go } from './lib/session.js';

// "/h/<id>" views a shared haul (always public). "/login" and "/signup"
// are the account screens (accounts live in the backend's users database). "/" creates a haul, once the
// visitor has logged in, signed up or chosen guest.
export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/';

  // A signed-in session is re-checked with the backend once per page load;
  // a token the server no longer knows sends the visitor back to log in.
  useEffect(() => {
    if (path.startsWith('/h/') || path === '/login' || path === '/signup' || !loadUser()) return;
    refreshUser().then((user) => { if (!user) go('/login'); });
  }, [path]);
  const share = path.match(/^\/h\/([A-Za-z0-9_-]+)$/);
  if (share) return <GuestHaul shareId={share[1]} />;
  if (path === '/login') return <AuthPage mode="login" />;
  if (path === '/signup') return <AuthPage mode="signup" />;
  if (!hasSession()) {
    window.history.replaceState(null, '', '/login');
    return <AuthPage mode="login" />;
  }
  return <HaulCreator />;
}
