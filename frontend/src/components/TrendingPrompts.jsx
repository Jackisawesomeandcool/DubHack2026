// Rectangular quick-search buttons to the left of the finder: aesthetics
// people are searching for right now. Each label runs a search phrased in
// pieces the catalog knows, so every chip returns something.
const TRENDING = [
  { label: 'Y2K', query: 'baggy cargo pants retro sneakers' },
  { label: 'gorpcore', query: 'fleece jacket trail shoes' },
  { label: 'old money', query: 'crewneck sweater cap' },
  { label: 'streetwear', query: 'hoodie joggers sneakers' },
  { label: 'quiet luxury', query: 'cardigan tee tote' },
  { label: 'retro runners', query: 'running shoes' },
];

export default function TrendingPrompts({ onPick, busy }) {
  return (
    <div className="trending" aria-label="Trending searches">
      <span className="trending__label">trending</span>
      {TRENDING.map((t) => (
        <button key={t.label} type="button" className="trending__btn" disabled={busy} onClick={() => onPick(t.query, t.label)} title={t.query}>
          {t.label}
        </button>
      ))}
    </div>
  );
}
