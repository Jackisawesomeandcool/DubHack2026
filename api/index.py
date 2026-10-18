"""Vercel entry point: every /api/* request runs backend/server.py's Handler (see vercel.json rewrites).

Hosted mode is switched on by Vercel's own VERCEL env var (config.HOSTED). Standard library only — Pillow,
numpy and onnxruntime are for the scraping / cropping tools and are never imported here.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("HAUL_HOSTED", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import server  # noqa: E402

server.boot_hosted()          # catalog.json -> SQLite in /tmp, once per cold start


class handler(server.Handler):
    """Vercel's Python runtime looks for a BaseHTTPRequestHandler subclass called `handler`."""
