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
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import auth
import catalog
import config
import cutouts
import finder
import fits
import llm
import colors
import seed
import stock
import store
from products import CATEGORIES

MAX_BODY = 2 * 1024 * 1024
MAX_PROMPT = 400


def _require_key(handler) -> bool:
    return True  # free web search works without any AI key


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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

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

    def _stream_suggest(self, prompt, category, exclude, models=False, ai=True):
        """NDJSON stream: {"items": [...]} then {"done": true}; an empty items list
        comes with a {"reason": "..."} event saying why (e.g. nothing under the budget)."""
        try:
            gen = finder.stream(prompt, category, exclude, models, ai=ai)
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

    def do_PUT(self):
        return self.do_POST()

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
            ai = body.get("ai", True) is not False      # the "AI-powered fits" switch in the search bar
            return self._stream_suggest(prompt, category, exclude, models, ai)

        if self.path.startswith("/api/auth/"):
            return self._auth_post()

        if self.path == "/api/me/state":
            body = self._read_json() or {}
            # sendBeacon (page close) can't set headers: the token may come in the body.
            tok = self._token() or (body.get("token") if isinstance(body.get("token"), str) else None)
            user = auth.user_for(tok)
            if not user:
                return self._json(HTTPStatus.UNAUTHORIZED, {"error": "not signed in"})
            try:
                return self._json(HTTPStatus.OK, auth.set_state(user["id"], body.get("favorites"), body.get("hauls"), body.get("history")))
            except auth.AuthError as err:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(err)})

        if self.path == "/api/seen":
            # Light stock re-check for products shown / placed on the board.
            body = self._read_json() or {}
            if not config.HOSTED:        # hosted: no background re-checks, stock comes from the dataset
                for url in [u for u in body.get("urls", []) if isinstance(u, str)][:20]:
                    stock.recheck(url)
            return self._json(HTTPStatus.OK, {"ok": True})

        if self.path == "/api/share":
            body = self._read_json()
            fits = store.sanitize_fits((body or {}).get("fits"))
            if not fits:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": "no fits to share"})
            try:
                return self._json(HTTPStatus.OK, {"id": store.save(fits)})
            except store.StoreUnavailable as err:
                return self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(err)})

        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _token(self) -> str | None:
        h = self.headers.get("Authorization", "")
        return h[7:].strip() if h.startswith("Bearer ") else None

    def _auth_post(self):
        body = self._read_json() or {}
        try:
            if self.path == "/api/auth/signup":
                user, token = auth.signup(body.get("firstName", ""), body.get("username", ""), body.get("email", ""), body.get("password", ""))
                print(f"[auth] new account @{user['username']} (users: {auth.count()})", file=sys.stderr)
                return self._json(HTTPStatus.OK, {"user": user, "token": token})
            if self.path == "/api/auth/login":
                user, token = auth.login(body.get("identifier", ""), body.get("password", ""))
                return self._json(HTTPStatus.OK, {"user": user, "token": token})
            if self.path == "/api/auth/logout":
                auth.logout(self._token())
                return self._json(HTTPStatus.OK, {"ok": True})
        except auth.AuthError as err:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": str(err)})
        return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_GET(self):
        if self.path == "/api/me/state":
            user = auth.user_for(self._token())
            if not user:
                return self._json(HTTPStatus.UNAUTHORIZED, {"error": "not signed in"})
            return self._json(HTTPStatus.OK, auth.get_state(user["id"]))
        if self.path == "/api/auth/me":
            user = auth.user_for(self._token())
            if not user:
                return self._json(HTTPStatus.UNAUTHORIZED, {"error": "not signed in"})
            return self._json(HTTPStatus.OK, {"user": user})
        if self.path == "/api/health":
            return self._json(HTTPStatus.OK, {
                "key": True,
                "ai": llm.configured(),
                "provider": llm.provider(),
                "cutouts": cutouts.available(),
                "catalog": catalog.count(),
                "users": 0 if config.HOSTED else auth.count(),
                "hosted": config.HOSTED,
            })
        if self.path.split("?")[0] == "/api/browse":
            m = re.search(r"[?&]n=(\d+)", self.path)
            n = int(m.group(1)) if m else 24
            return self._json(HTTPStatus.OK, {"items": catalog.random_items(n)})
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
            # hosted: the images ship inside the deployment (backend/dataset/cutouts), not in /tmp
            folder = Path(config.BACKEND_DIR) / "dataset" / "cutouts" if config.HOSTED else cutouts.CUTOUT_DIR
            return self._serve_file(folder / m.group(1), "image/png")
        self._serve_static()

    def _serve_file(self, path, ctype):
        if not path.is_file():
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # s-maxage lets Vercel's CDN keep the image, so repeat views do not run the function
        self.send_header("Cache-Control", "public, max-age=31536000, s-maxage=31536000, immutable")
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


_boot_lock = threading.Lock()
_booted = False


def boot_hosted() -> None:
    """Serverless cold start: build the catalog (in /tmp) from backend/dataset/catalog.json. No threads, no images."""
    global _booted
    with _boot_lock:
        if _booted:
            return
        import dataset
        stats = dataset.load(quiet=True, images=False)
        print(f"[hosted] catalog ready: {catalog.count()} products ({stats['added']} loaded)", file=sys.stderr)
        _booted = True


def quality_sweep() -> None:
    """Background: drop catalog cutouts that still show a person (local detector, no key)."""
    import threading
    from pathlib import Path

    def run():
        try:
            import quality
            if not quality.available():
                return
            with catalog._lock:
                rows = catalog._db().execute("SELECT url, name, cutout_p FROM products WHERE cutout_p LIKE '/cutouts/%'").fetchall()
            bad, shredded = [], []
            for url, name, cp in rows:
                path = Path(config.DATA_DIR) / "cutouts" / Path(cp).name
                broken, why = quality.broken_cutout(path)
                if broken:
                    shredded.append(url)
                    print(f"[quality] {why}, removing: {name}", file=sys.stderr)
                    continue
                ok, _ = quality.check_cutout(path)
                if not ok:
                    bad.append(url)
                    print(f"[quality] person in cutout, dropping: {name}", file=sys.stderr)
            if bad:
                with catalog._lock:
                    catalog._db().executemany("UPDATE products SET cutout_p=NULL WHERE url=?", [(u,) for u in bad])
                    catalog._db().commit()
            if shredded:
                import view_catalog
                view_catalog.remove(shredded)   # blocked for good, synced to the shared dataset on export
            print(f"[quality] checked {len(rows)} cutouts · {len(bad)} dropped · {len(shredded)} removed", file=sys.stderr)
        except Exception as err:  # noqa: BLE001
            print(f"[quality] sweep failed: {err}", file=sys.stderr)

    threading.Thread(target=run, daemon=True).start()


def main() -> None:
    ranker_name = llm.provider() if llm.configured() else "keywords (set GEMINI_API_KEY for AI picks)"
    mode = f"catalog search · ranked by {ranker_name}"
    print(f"Haul Curator API on http://{config.HOST}:{config.PORT}  —  {mode}")
    print(f"catalog: {catalog.count()} items · cutouts: flat-key + {config.CUTOUT_PROVIDER} · {colors.progress()}")
    cutouts.warm()
    seed.warm()
    quality_sweep()
    colors.sweep()          # background: read each product's color from its image (see colors.py)
    # (no catalog warm-up: search is catalog-only, nothing to pre-fetch)
    stock.start()
    fits.ensure_pool()
    ThreadingHTTPServer((config.HOST, config.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
