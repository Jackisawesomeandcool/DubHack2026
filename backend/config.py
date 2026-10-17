"""Server-side configuration. Secrets are read from the environment or backend/.env only."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
ROOT_DIR = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE per line) so no extra dependency is needed."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(BACKEND_DIR / ".env")

XAI_API_KEY = os.environ.get("XAI_API_KEY", "").strip()
# Web search + structured output need a Grok 4 family model.
XAI_MODEL = os.environ.get("XAI_MODEL", "grok-4.7").strip()
# Lower reasoning effort = faster curation. Set empty to use the model default.
XAI_REASONING = os.environ.get("XAI_REASONING", "low").strip()
# Model used for the photo check (needs image input). Defaults to XAI_MODEL.
XAI_VISION_MODEL = os.environ.get("XAI_VISION_MODEL", "").strip() or XAI_MODEL
# Restrict curation to these retailer domains (comma-separated, max 5). Empty = whole web.
ALLOWED_DOMAINS = [d.strip() for d in os.environ.get("ALLOWED_DOMAINS", "nike.com").split(",") if d.strip()][:5]
XAI_BASE_URL = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")

# Background removal. Product-only photos on flat backgrounds are keyed locally
# (free, instant). For everything else: "photoroom" or "removebg" if a key is
# set (fast, ~1-2 s, paid per image), otherwise local rembg (free, slow).
PHOTOROOM_API_KEY = os.environ.get("PHOTOROOM_API_KEY", "").strip()
REMOVEBG_API_KEY = os.environ.get("REMOVEBG_API_KEY", "").strip()
CUTOUT_PROVIDER = os.environ.get("CUTOUT_PROVIDER", "").strip().lower() or (
    "photoroom" if PHOTOROOM_API_KEY else "removebg" if REMOVEBG_API_KEY else "local")

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

DATA_DIR = BACKEND_DIR / "data"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
