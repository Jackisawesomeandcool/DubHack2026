// Past prompts as small bubbles at the bottom-left of the page, newest at the
// bottom (like a search history). Clicking one brings its options back; hovering
// one shows a small × that removes it from the history.
export default function SearchHistory({ entries, activeId, onSelect, onDelete }) {
  if (entries.length === 0) return null;
  return (
    <aside className="history" aria-label="Search history">
      {[...entries].reverse().map((e) => (
        <div key={e.id} className="bubble-wrap">
          <button
            type="button"
            className={`bubble${e.id === activeId ? ' is-active' : ''}${e.loading ? ' is-loading' : ''}${e.error ? ' is-error' : ''}`}
            onClick={() => onSelect(e.id)}
            title={e.prompt}
          >
            <svg className="bubble__icon" viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
              <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
              <path d="M8 4.6V8l2.3 1.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
            <span className="bubble__text">{e.prompt}</span>
            {e.loading && <span className="bubble__dots"><i /><i /><i /></span>}
          </button>
          {onDelete && (
            <button
              type="button"
              className="bubble__del"
              onClick={() => onDelete(e.id)}
              aria-label={`Remove “${e.prompt}” from search history`}
              title="Remove from history"
            >
              ×
            </button>
          )}
        </div>
      ))}
    </aside>
  );
}
