import { useEffect, useState } from 'react';

// Slanted date / time box in the top-right, like the Persona pause menu.
function phase(h) {
  if (h < 5) return 'DARK HOUR';
  if (h < 11) return 'MORNING';
  if (h < 14) return 'LUNCHTIME';
  if (h < 17) return 'AFTERNOON';
  if (h < 20) return 'EVENING';
  return 'NIGHT';
}

export default function DateTag() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 15000);
    return () => clearInterval(t);
  }, []);

  const date = `${now.getMonth() + 1}/${now.getDate()}`;
  const day = now.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
  const time = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="datetag" aria-hidden="true">
      <span className="datetag__date">{date}</span>
      <span className="datetag__strip">{day} · {phase(now.getHours())} · {time}</span>
    </div>
  );
}
