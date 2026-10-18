import HaulCreator from './components/HaulCreator.jsx';
import GuestHaul from './components/GuestHaul.jsx';
import AuthPage from './components/AuthPage.jsx';
import VibesPage from './components/VibesPage.jsx';
import { hasSession } from './lib/session.js';

// "/h/<id>" views a shared haul (always public). "/login", "/signup" and
// "/welcome" are the demo account screens. "/" creates a haul, once the
// visitor has logged in, signed up or chosen guest.
export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/';
  const share = path.match(/^\/h\/([A-Za-z0-9_-]+)$/);
  if (share) return <GuestHaul shareId={share[1]} />;
  if (path === '/login') return <AuthPage mode="login" />;
  if (path === '/signup') return <AuthPage mode="signup" />;
  if (path === '/welcome') return <VibesPage />;
  if (!hasSession()) {
    window.history.replaceState(null, '', '/login');
    return <AuthPage mode="login" />;
  }
  return <HaulCreator />;
}
