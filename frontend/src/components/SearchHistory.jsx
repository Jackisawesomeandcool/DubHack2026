// Past prompts as small speech bubbles beside the board. Clicking one brings
// its options back into the tray.
export default function SearchHistory({ entries, activeId, onSelect }) {
  if (entries.length === 0) return null;
  return (
    <aside className="history" aria-label="Search history">
      {entries.map((e) => (
        <button
          key={e.id}
          type="button"
          className={`bubble${e.id === activeId ? ' is-active' : ''}${e.loading ? ' is-loading' : ''}${e.error ? ' is-error' : ''}`}
          onClick={() => onSelect(e.id)}
          title={e.prompt}
        >
          {e.prompt}
          {e.loading && <span className="bubble__dots"><i /><i /><i /></span>}
        </button>
      ))}
    </aside>
  );
}
