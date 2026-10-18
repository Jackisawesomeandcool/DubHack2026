import HaulCreator from './components/HaulCreator.jsx';
import GuestHaul from './components/GuestHaul.jsx';

// Exactly two experiences: "/" creates a haul, "/h/<id>" views a shared one.
export default function App() {
  const match = window.location.pathname.match(/^\/h\/([A-Za-z0-9_-]+)\/?$/);
  return match ? <GuestHaul shareId={match[1]} /> : <HaulCreator />;
}
