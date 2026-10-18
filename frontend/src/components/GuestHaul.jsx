import { useEffect, useMemo, useState } from 'react';
import FitSelector from './FitSelector.jsx';
import HaulTotal from './HaulTotal.jsx';
import Backdrop from './Backdrop.jsx';
import FashionCanvas from './FashionCanvas.jsx';
import { loadShare } from '../lib/api.js';
import { fitTotal, withPositions } from '../lib/haul.js';
import ThemeControl from './ThemeControl.jsx';

// Read-only view of a shared haul: same board, same hover and click, no finder.
export default function GuestHaul({ shareId }) {
  const [fits, setFits] = useState(null);
  const [current, setCurrent] = useState(0);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    loadShare(shareId)
      .then((data) => setFits((data.fits || []).map((f) => ({ items: withPositions(f.items) }))))
      .catch(() => setMissing(true));
  }, [shareId]);

  const fit = fits?.[current];
  const total = useMemo(() => fitTotal(fit), [fit]);

  return (
    <main className="app is-guest">
      <Backdrop index={current} />
      <header className="bar">
        <div className="bar__right">
          <HaulTotal total={total} />
          <ThemeControl />
        </div>
      </header>

      <div className="stage">
        <FitSelector fits={fits || []} current={current} onSelect={setCurrent} />
        <FashionCanvas
          items={fit?.items || []}
          fitKey={current}
          loading={!fits && !missing}
          hint={missing ? 'this haul link doesn’t exist' : ''}
        />
      </div>
    </main>
  );
}
