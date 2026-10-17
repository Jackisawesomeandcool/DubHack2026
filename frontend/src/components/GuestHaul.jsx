import { useEffect, useMemo, useState } from 'react';
import FitSelector from './FitSelector.jsx';
import HaulTotal from './HaulTotal.jsx';
import FashionCanvas from './FashionCanvas.jsx';
import { loadShare } from '../lib/api.js';
import { fitTotal } from '../lib/haul.js';

// Read-only view of a shared haul: same collage, same hover and click, no prompt bar.
export default function GuestHaul({ shareId }) {
  const [fits, setFits] = useState(null);
  const [current, setCurrent] = useState(0);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    loadShare(shareId)
      .then((data) => setFits(data.fits || []))
      .catch(() => setMissing(true));
  }, [shareId]);

  const fit = fits?.[current];
  const total = useMemo(() => fitTotal(fit), [fit]);

  return (
    <main className="app is-guest">
      <header className="bar">
        <FitSelector fits={fits || []} current={current} onSelect={setCurrent} />
        <div className="bar__right">
          <HaulTotal total={total} />
        </div>
      </header>

      <FashionCanvas
        items={fit?.items || []}
        fitKey={current}
        busy={!fits && !missing}
        emptyHint={missing ? 'this haul link doesn’t exist' : ''}
      />
    </main>
  );
}
