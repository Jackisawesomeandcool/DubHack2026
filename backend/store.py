"""Tiny JSON-file store for shared hauls."""

import json
import secrets
import threading

import config
import kv
from products import normalize_list

MAX_FITS = 5
_lock = threading.Lock()
_path = config.DATA_DIR / "shares.json"


def _read() -> dict:
    if not _path.exists():
        return {}
    try:
        return json.loads(_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(_path)


def sanitize_fits(fits) -> list[dict]:
    if not isinstance(fits, list):
        return []
    clean = []
    for fit in fits[:MAX_FITS]:
        items = normalize_list(fit.get("items") if isinstance(fit, dict) else None)
        if items:
            clean.append({"items": items})
    return clean


class StoreUnavailable(RuntimeError):
    """Sharing needs storage that isn't connected (hosted without Upstash) or isn't reachable."""


def save(fits: list[dict]) -> str:
    if kv.enabled() or config.HOSTED:
        if not kv.enabled():
            raise StoreUnavailable("Sharing isn't available on this deployment yet (storage not connected).")
        try:
            for _ in range(5):
                share_id = secrets.token_urlsafe(6)
                if kv.set_json(f"haul:share:{share_id}", {"fits": fits}, "NX") is not None:
                    return share_id
        except kv.KVError as err:
            raise StoreUnavailable("Couldn't create a share link right now.") from err
        raise StoreUnavailable("Couldn't create a share link right now.")
    with _lock:
        data = _read()
        share_id = secrets.token_urlsafe(6)
        while share_id in data:
            share_id = secrets.token_urlsafe(6)
        data[share_id] = {"fits": fits}
        _write(data)
    return share_id


def load(share_id: str) -> dict | None:
    if kv.enabled() or config.HOSTED:
        if not kv.enabled():
            return None
        try:
            return kv.get_json(f"haul:share:{share_id}")
        except kv.KVError:
            return None
    with _lock:
        return _read().get(share_id)
