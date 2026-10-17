"""Haul Curator API — standard library only.

    GET  /api/random-fit                              -> {"prompt": "...", "items": [...]}
    POST /api/suggest   {"prompt": "...", "category"?: "shoes", "exclude"?: [names]}
                        -> {"items": [...options...]}
    POST /api/share           {"fits": [{"items":[...]}]} -> {"id": "..."}
    GET  /api/share/<id>                              -> {"fits": [...]}

Also serves frontend/dist when it exists (production-style single process).
"""

import json
import mimetypes
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import catalog
import config
import cutouts
import finder
import fits
import llm
import stock
import store
from products import CATEGORIES

MAX_BODY = 256 * 1024
MAX_PROMPT = 400


def _require_key(handler) -> bool:
    if llm.configured():
        return True
    handler._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "GEMINI_API_KEY not configured"})
    return False


class Handler(BaseHTTPRequestHandler):
    server_version = "HaulCurator/1.0"

    # ---- helpers -----------------------------------------------------------
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY:
            return None
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _stream_suggest(self, prompt, category, exclude, models=False):
        """NDJSON stream: products first, then one line per finished cutout."""
        try:
            gen = finder.stream(prompt, category, exclude, models)
            first = next(gen)
        except (llm.LLMError, StopIteration) as err:
            print(f"[ai] {err}", file=sys.stderr)
            return self._json(HTTPStatus.BAD_GATEWAY, {"error": str(err) or "no results"})
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        try:
            self.wfile.write((json.dumps(first) + "\n").encode("utf-8"))
            self.wfile.flush()
            for ev in gen:  # lazily, so each cutout ships the moment it's ready
                self.wfile.write((json.dumps(ev) + "\n").encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away

    def log_message(self, fmt, *args):  # quieter logs
        print(f"{self.command} {self.path} {args[1] if len(args) > 1 else ''}", file=sys.stderr)

    # ---- routes ------------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/suggest":
            body = self._read_json() or {}
            prompt = str(body.get("prompt", "")).strip()[:MAX_PROMPT]
            if not prompt:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "prompt required"})
            category = body.get("category")
            category = category if category in CATEGORIES else None
            exclude = [str(n)[:120] for n in body.get("exclude", []) if isinstance(n, str)][:12]
            models = bool(body.get("models", False))
            if not _require_key(self):
                return None
            return self._stream_suggest(prompt, category, exclude, models)

        if self.path == "/api/seen":
            # Light stock re-check for products shown / placed on the board.
            body = self._read_json() or {}
            for url in [u for u in body.get("urls", []) if isinstance(u, str)][:20]:
                stock.recheck(url)
            return self._json(HTTPStatus.OK, {"ok": True})

        if self.path == "/api/share":
            body = self._read_json()
            fits = store.sanitize_fits((body or {}).get("fits"))
            if not fits:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "no fits to share"})
            return self._json(HTTPStatus.OK, {"id": store.save(fits)})

        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_GET(self):
        if self.path == "/api/health":
            return self._json(HTTPStatus.OK, {
                "key": llm.configured(),
                "provider": llm.provider(),
                "cutouts": cutouts.available(),
                "catalog": catalog.count(),
            })
        if self.path.split("?")[0] == "/api/random-fit":
            if not _require_key(self):
                return None
            models = "models=1" in self.path
            try:
                return self._json(HTTPStatus.OK, fits.take(models))
            except llm.LLMError as err:
                print(f"[ai] {err}", file=sys.stderr)
                return self._json(HTTPStatus.BAD_GATEWAY, {"error": str(err)})
        m = re.fullmatch(r"/api/share/([A-Za-z0-9_-]{4,32})", self.path)
        if m:
            shared = store.load(m.group(1))
            if not shared:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "haul not found"})
            return self._json(HTTPStatus.OK, shared)
        if self.path.startswith("/api/"):
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        m = re.fullmatch(r"/cutouts/([a-f0-9]{16}\.png)", self.path)
        if m:
            return self._serve_file(cutouts.CUTOUT_DIR / m.group(1), "image/png")
        self._serve_static()

    def _serve_file(self, path, ctype):
        if not path.is_file():
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self):
        dist = config.FRONTEND_DIST
        if not dist.exists():
            return self._json(HTTPStatus.NOT_FOUND, {"error": "frontend not built; run the Vite dev server"})
        rel = self.path.split("?", 1)[0].lstrip("/")
        target = (dist / rel).resolve() if rel else dist / "index.html"
        if not str(target).startswith(str(dist.resolve())) or not target.is_file():
            target = dist / "index.html"  # SPA fallback (/h/<id>)
        data = Path(target).read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    mode = f"AI: {llm.provider()} · stores: {', '.join(config.ALLOWED_DOMAINS) or 'any'}" if llm.configured() else "NO KEY — set GEMINI_API_KEY in backend/.env"
    print(f"Haul Curator API on http://{config.HOST}:{config.PORT}  —  {mode}")
    print(f"catalog: {catalog.count()} items · cutouts: flat-key + {config.CUTOUT_PROVIDER}")
    cutouts.warm()
    catalog.warm(lambda term, models: finder.find(term, models, local_first=False))
    stock.start()
    fits.ensure_pool()
    ThreadingHTTPServer((config.HOST, config.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
