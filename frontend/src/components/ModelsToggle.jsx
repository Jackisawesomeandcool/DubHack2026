// Whether new fits and search results may show the item worn on a model
// (on) or must be product-only cutouts (off). Applies to what's pulled next;
// pieces already on the board stay as they are.
export default function ModelsToggle({ value, onChange }) {
  return (
    <button
      type="button"
      className={`toggle${value ? ' is-on' : ''}`}
      role="switch"
      aria-checked={value}
      aria-label="Show items on models"
      title={value ? 'Showing items on models' : 'Showing items only'}
      onClick={() => onChange(!value)}
    >
      <span className="toggle__label">models</span>
      <span className="toggle__track" aria-hidden="true"><span className="toggle__knob" /></span>
    </button>
  );
}
