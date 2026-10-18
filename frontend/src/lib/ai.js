// Who suggested a piece. The backend tags AI-ranked results with `by` ("gemini" / "xai") and, when the
// model gave one, a one-line reason in `why`. Keyword results carry neither.
const NAMES = { gemini: 'Gemini', xai: 'Grok' };

export function aiName(item) {
  return item && NAMES[item.by] ? NAMES[item.by] : null;
}
