"""Tiny Upstash Redis client over its REST API (standard library only, no card needed).

Used for accounts, per-user state and shared hauls when the site is hosted on Vercel, where the
filesystem is wiped between requests. Locally nothing here is used: SQLite / JSON files stay as they are.

Set these (Vercel > Settings > Environment Variables, or the Upstash integration does it for you):
    UPSTASH_REDIS_REST_URL    UPSTASH_REDIS_REST_TOKEN        (Vercel's older KV_REST_API_URL / KV_REST_API_TOKEN work too)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

TIMEOUT = 8


class KVError(RuntimeError):
    """Redis unreachable or rejected the command."""


def _creds() -> tuple[str, str]:
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL") or ""
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN") or ""
    return url.strip().rstrip("/"), token.strip()


def enabled() -> bool:
    url, token = _creds()
    return bool(url and token)


def _arg(a):
    return a if isinstance(a, (int, float)) else str(a)


def _post(path: str, payload):
    url, token = _creds()
    if not (url and token):
        raise KVError("storage is not configured")
    req = urllib.request.Request(
        url + path, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:200]
        raise KVError(f"storage error {err.code}: {detail}") from err
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as err:
        raise KVError(f"storage unreachable: {err}") from err


def cmd(*args):
    """Run one Redis command, e.g. cmd("SET", "k", "v", "NX", "EX", 60). Returns the decoded result."""
    out = _post("", [_arg(a) for a in args])
    if isinstance(out, dict) and "error" in out:
        raise KVError(str(out["error"]))
    return out.get("result") if isinstance(out, dict) else out


def pipeline(*commands):
    """Several commands in one HTTP round trip (each still counts toward the daily quota)."""
    out = _post("/pipeline", [[_arg(a) for a in c] for c in commands])
    results = []
    for entry in out if isinstance(out, list) else []:
        if isinstance(entry, dict) and "error" in entry:
            raise KVError(str(entry["error"]))
        results.append(entry.get("result") if isinstance(entry, dict) else entry)
    return results


def get_json(key: str):
    raw = cmd("GET", key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def set_json(key: str, value, *extra):
    return cmd("SET", key, json.dumps(value, separators=(",", ":")), *extra)
