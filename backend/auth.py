"""Accounts, in their own database: backend/data/users.sqlite.

Kept apart from catalog.sqlite on purpose — the catalog is rebuilt and exported
by the scraping tools, and user data must never ride along with that.

    users     id, username (unique, lowercase), email (unique, lowercase),
              first_name, password_hash, salt, created_at
    sessions  token, user_id, created_at, last_seen
    state     user_id, favorites (JSON), hauls (JSON), updated_at
              — everything a signed-in user builds: starred listings and
              their haul boards (pieces + positions), reloaded on login

Passwords are hashed with scrypt (standard library, no extra packages); a
session token is a random 32-byte string the browser sends back as
`Authorization: Bearer <token>`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import sys
import threading
import time

import config
import kv

DB_PATH = config.DATA_DIR / "users.sqlite"
USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,20}$")
EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")
MIN_PASSWORD = 8
SESSION_TTL = 30 * 24 * 3600  # 30 days

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


class AuthError(Exception):
    """A user-facing problem (bad input, wrong password, taken username)."""


def _remote() -> bool:
    """True when accounts live in Upstash Redis (hosted). Hosted without storage = accounts unavailable,
    never a silent per-instance database that would forget everyone."""
    if kv.enabled():
        return True
    if config.HOSTED:
        raise AuthError("Accounts aren't available on this deployment yet (storage not connected).")
    return False


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                first_name TEXT NOT NULL,
                password_hash BLOB NOT NULL,
                salt BLOB NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at REAL NOT NULL,
                last_seen REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE TABLE IF NOT EXISTS state (
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                favorites TEXT NOT NULL DEFAULT '[]',
                hauls TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL
            );
        """)
        cols = {r[1] for r in _conn.execute("PRAGMA table_info(state)").fetchall()}
        if "history" not in cols:
            _conn.execute("ALTER TABLE state ADD COLUMN history TEXT NOT NULL DEFAULT '[]'")
            _conn.commit()
    return _conn


# ---------------------------------------------------------------- passwords
def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def _public(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "username": row["username"], "email": row["email"], "firstName": row["first_name"]}


# ---------------------------------------------------------------- accounts
def signup(first_name: str, username: str, email: str, password: str) -> tuple[dict, str]:
    """Create an account; returns (user, session token)."""
    first_name = (first_name or "").strip()[:40]
    username = (username or "").strip().lstrip("@").lower()
    email = (email or "").strip().lower()
    if not first_name:
        raise AuthError("Enter your first name.")
    if not USERNAME_RE.fullmatch(username):
        raise AuthError("Usernames are 3–20 characters: letters, numbers, _ or .")
    if not EMAIL_RE.fullmatch(email) or len(email) > 120:
        raise AuthError("Enter a valid email.")
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"Password needs at least {MIN_PASSWORD} characters.")
    if _remote():
        import auth_kv
        try:
            return auth_kv.signup(first_name, username, email, password)
        except kv.KVError as err:
            print(f"[auth] storage: {err}", file=sys.stderr)
            raise AuthError("Accounts are unavailable for a moment — try again shortly.") from err
    salt = secrets.token_bytes(16)
    now = time.time()
    with _lock:
        db = _db()
        if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise AuthError("That username is taken.")
        if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise AuthError("An account with that email already exists — log in instead.")
        cur = db.execute(
            "INSERT INTO users (username, email, first_name, password_hash, salt, created_at) VALUES (?,?,?,?,?,?)",
            (username, email, first_name, _hash(password, salt), salt, now))
        user_id = cur.lastrowid
        token = _new_session(db, user_id, now)
        db.commit()
        row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return _public(row), token


def login(identifier: str, password: str) -> tuple[dict, str]:
    """Email or username + password; returns (user, session token)."""
    ident = (identifier or "").strip().lstrip("@").lower()
    if not ident or not password:
        raise AuthError("Enter your email or username and password.")
    if _remote():
        import auth_kv
        try:
            return auth_kv.login(ident, password)
        except kv.KVError as err:
            print(f"[auth] storage: {err}", file=sys.stderr)
            raise AuthError("Accounts are unavailable for a moment — try again shortly.") from err
    with _lock:
        db = _db()
        row = db.execute("SELECT * FROM users WHERE email=? OR username=?", (ident, ident)).fetchone()
        # Same work and same message whether the account exists or not.
        salt = row["salt"] if row else b"\0" * 16
        ok = row is not None and hmac.compare_digest(_hash(password, salt), row["password_hash"])
        if not ok:
            raise AuthError("Wrong email/username or password.")
        token = _new_session(db, row["id"], time.time())
        db.commit()
    return _public(row), token


def _new_session(db: sqlite3.Connection, user_id: int, now: float) -> str:
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions (token, user_id, created_at, last_seen) VALUES (?,?,?,?)", (token, user_id, now, now))
    return token


def user_for(token: str | None) -> dict | None:
    """The signed-in user for a session token, or None."""
    if not token:
        return None
    if kv.enabled() or config.HOSTED:
        if not kv.enabled():
            return None
        import auth_kv
        try:
            return auth_kv.user_for(token)
        except kv.KVError as err:
            print(f"[auth] storage: {err}", file=sys.stderr)
            return None
    now = time.time()
    with _lock:
        db = _db()
        row = db.execute(
            "SELECT u.*, s.last_seen FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token=?", (token,)).fetchone()
        if not row or now - row["last_seen"] > SESSION_TTL:
            if row:
                db.execute("DELETE FROM sessions WHERE token=?", (token,))
                db.commit()
            return None
        db.execute("UPDATE sessions SET last_seen=? WHERE token=?", (now, token))
        db.commit()
    return _public(row)


def logout(token: str | None) -> None:
    if not token:
        return
    if kv.enabled() or config.HOSTED:
        if kv.enabled():
            import auth_kv
            try:
                auth_kv.logout(token)
            except kv.KVError:
                pass
        return
    with _lock:
        _db().execute("DELETE FROM sessions WHERE token=?", (token,))
        _db().commit()


def count() -> int:
    if kv.enabled() or config.HOSTED:
        if not kv.enabled():
            return 0
        import auth_kv
        try:
            return auth_kv.count()
        except kv.KVError:
            return 0
    with _lock:
        return _db().execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ---------------------------------------------------------------- deleting what the user stored
def clear_data(user_id: int) -> None:
    """Remove the user's saved favorites, hauls and search history; the account stays."""
    if _remote():
        import auth_kv
        try:
            return auth_kv.clear_data(user_id)
        except kv.KVError as err:
            raise AuthError("Couldn't clear your data right now — try again in a moment.") from err
    with _lock:
        _db().execute("DELETE FROM state WHERE user_id=?", (user_id,))
        _db().commit()


def delete_account(user_id: int) -> None:
    """Remove the account, every session and everything saved with it. Share links already created are
    anonymous snapshots (not tied to an account) and stay viewable."""
    if _remote():
        import auth_kv
        try:
            return auth_kv.delete_account(user_id)
        except kv.KVError as err:
            raise AuthError("Couldn't delete the account right now — try again in a moment.") from err
    with _lock:
        db = _db()
        db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM state WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()


# ---------------------------------------------------------------- per-user state
MAX_STATE_BYTES = 2_000_000
MAX_STATE_BYTES_REMOTE = 900_000   # Upstash's free plan caps a request at 1 MB


def _loads(text: str) -> list:
    try:
        v = json.loads(text or "[]")
        return v if isinstance(v, list) else []
    except json.JSONDecodeError:
        return []


def get_state(user_id: int) -> dict:
    if _remote():
        import auth_kv
        try:
            return auth_kv.get_state(user_id)
        except kv.KVError as err:
            raise AuthError("Couldn't load your saved data right now.") from err
    with _lock:
        row = _db().execute("SELECT favorites, hauls, history, updated_at FROM state WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return {"favorites": [], "hauls": [], "history": [], "updatedAt": None}
    return {"favorites": _loads(row["favorites"]), "hauls": _loads(row["hauls"]), "history": _loads(row["history"]),
            "updatedAt": row["updated_at"]}


def set_state(user_id: int, favorites, hauls, history=None) -> dict:
    """Replace the user's favorites, hauls and search history (whole snapshot, last write wins)."""
    favorites = [f for f in (favorites or []) if isinstance(f, dict)][:200]
    hauls = [h for h in (hauls or []) if isinstance(h, dict) and isinstance(h.get("items"), list)][:5]
    history = [h for h in (history or []) if isinstance(h, dict) and isinstance(h.get("prompt"), str)][:7]
    fav_s, haul_s, hist_s = json.dumps(favorites), json.dumps(hauls), json.dumps(history)
    if len(fav_s) + len(haul_s) + len(hist_s) > (MAX_STATE_BYTES if not _remote() else MAX_STATE_BYTES_REMOTE):
        raise AuthError("Too much data to save.")
    if _remote():
        import auth_kv
        try:
            return auth_kv.set_state(user_id, favorites, hauls, history)
        except kv.KVError as err:
            raise AuthError("Couldn't save right now — try again in a moment.") from err
    now = time.time()
    with _lock:
        _db().execute(
            "INSERT INTO state (user_id, favorites, hauls, history, updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET favorites=excluded.favorites, hauls=excluded.hauls, "
            "history=excluded.history, updated_at=excluded.updated_at",
            (user_id, fav_s, haul_s, hist_s, now))
        _db().commit()
    return {"ok": True, "updatedAt": now}
