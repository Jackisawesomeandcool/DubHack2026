"""Haul Curator API — standard library only.

    POST /api/curate          {"prompt": "..."}       -> {"items": [...], "source": "grok"|"demo"}
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
import grok
import store

MAX_BODY = 256 * 1024
MAX_PROMPT = 400


def _curate(prompt: str) -> tuple[list[dict], str]:
    if config.XAI_API_KEY:
        try:
            return grok.curate(prompt), "grok"
        except grok.GrokError as err:
            print(f"[grok] {err} — falling back to demo catalog", file=sys.stderr)
    return catalog.curate(prompt), "demo"


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

    def log_message(self, fmt, *args):  # quieter logs
        print(f"{self.command} {self.path} {args[1] if len(args) > 1 else ''}", file=sys.stderr)

    # ---- routes ------------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/curate":
            body = self._read_json()
            prompt = str((body or {}).get("prompt", "")).strip()[:MAX_PROMPT]
            if not prompt:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "prompt required"})
            items, source = _curate(prompt)
            return self._json(HTTPStatus.OK, {"items": items, "source": source})

        if self.path == "/api/share":
            body = self._read_json()
            fits = store.sanitize_fits((body or {}).get("fits"))
            if not fits:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "no fits to share"})
            return self._json(HTTPStatus.OK, {"id": store.save(fits)})

        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_GET(self):
        m = re.fullmatch(r"/api/share/([A-Za-z0-9_-]{4,32})", self.path)
        if m:
            shared = store.load(m.group(1))
            if not shared:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "haul not found"})
            return self._json(HTTPStatus.OK, shared)
        if self.path.startswith("/api/"):
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        self._serve_static()

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
    mode = "Grok (xAI)" if config.XAI_API_KEY else "demo catalog (set XAI_API_KEY to enable Grok)"
    print(f"Haul Curator API on http://{config.HOST}:{config.PORT}  —  curation: {mode}")
    ThreadingHTTPServer((config.HOST, config.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
