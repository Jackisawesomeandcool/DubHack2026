"""ASGI entry point for Vercel (the `backend` service in vercel.json).

The API is written on the standard library's BaseHTTPRequestHandler (server.py); this thin adapter runs that
same Handler for each ASGI request, so local `python3 server.py` and the hosted site share one code path.
Nothing here needs a third-party package.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
from urllib.parse import quote

os.environ.setdefault("HAUL_HOSTED", "1")

import server  # noqa: E402

server.boot_hosted()          # catalog.json -> SQLite in /tmp, once per cold start

_DROP = {"connection", "date", "server", "transfer-encoding", "content-length"}


class _Shim(server.Handler):
    """Handler fed from bytes instead of a socket."""

    def __init__(self, raw: bytes):
        self._raw = raw
        self._out = io.BytesIO()
        super().__init__(None, ("0.0.0.0", 0), None)       # runs setup() -> handle() -> finish()

    def setup(self):
        self.rfile = io.BytesIO(self._raw)
        self.wfile = self._out

    def finish(self):
        pass


def _dispatch(scope: dict, body: bytes) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    path = scope.get("raw_path") or quote(scope.get("path", "/")).encode()
    target = path.decode("latin-1")
    if scope.get("query_string"):
        target += "?" + scope["query_string"].decode("latin-1")
    lines = [f"{scope['method']} {target} HTTP/1.1"]
    for k, v in scope.get("headers", []):
        if k.decode("latin-1").lower() not in ("content-length", "transfer-encoding", "connection"):
            lines.append(f"{k.decode('latin-1')}: {v.decode('latin-1')}")
    lines += [f"Content-Length: {len(body)}", "Connection: close"]
    raw = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body
    try:
        out = _Shim(raw)._out.getvalue()
    except Exception as err:  # noqa: BLE001
        print(f"[hosted] handler failed: {err!r}", file=sys.stderr)
        return 500, [(b"content-type", b"application/json")], b'{"error": "server error"}'
    head, _, payload = out.partition(b"\r\n\r\n")
    status_line, *header_lines = head.decode("latin-1").split("\r\n")
    status = int(status_line.split()[1])
    headers = []
    for line in header_lines:
        name, _, value = line.partition(":")
        if name.strip().lower() not in _DROP:
            headers.append((name.strip().lower().encode(), value.strip().encode("latin-1")))
    return status, headers, payload


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body"):
            break
    status, headers, payload = await asyncio.get_running_loop().run_in_executor(None, _dispatch, scope, body)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})
