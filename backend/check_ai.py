"""Is Gemini reachable with the key in backend/.env? Run: python3 backend/check_ai.py

Makes one tiny request (no catalog, nothing written) and prints exactly what came back, so a quota,
model-name or network problem is obvious. The key itself is never printed."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import llm  # noqa: E402

print(f"provider : {llm.provider() or '(none)'}")
print(f"key      : {'set (' + str(len(config.GEMINI_API_KEY)) + ' chars)' if config.GEMINI_API_KEY else 'MISSING — add GEMINI_API_KEY to backend/.env'}")
print(f"model    : {config.GEMINI_MODEL}")
if not llm.configured():
    sys.exit(1)

lines = ["1 | Nike | Tech Fleece Hoodie | $120 | top | black", "2 | Uniqlo | Straight Jeans | $60 | bottom | blue"]
t0 = time.time()
try:
    picks = llm.pick_products("a cozy black hoodie", lines, 2)
except Exception as err:  # noqa: BLE001
    print(f"FAILED after {time.time() - t0:.1f}s: {err}")
    sys.exit(2)
print(f"OK in {time.time() - t0:.1f}s: {picks}")
