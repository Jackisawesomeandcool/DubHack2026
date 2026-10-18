"""Accounts on Upstash Redis — the hosted twin of the SQLite code in auth.py (same behaviour, same messages).

Keys
    haul:uid                 counter for user ids
    haul:name:<username>     -> user id      (claimed with SET NX, so two signups cannot take the same name)
    haul:mail:<email>        -> user id
    haul:user:<id>           -> JSON {id, username, email, firstName, ph, salt, createdAt}
    haul:sess:<token>        -> JSON public user, expires after SESSION_TTL (renewed on every use)
    haul:state:<id>          -> JSON {favorites, hauls, history, updatedAt}
auth.py calls into this module; it is not used locally.
"""

from __future__ import annotations

import hmac
import json
import secrets
import time

import kv

P = "haul:"


def _auth():
    import auth          # imported lazily: auth imports this module too
    return auth


def _public(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"], "email": u["email"], "firstName": u["firstName"]}


def _new_session(user: dict) -> str:
    token = secrets.token_urlsafe(32)
    ttl = _auth().SESSION_TTL
    # the per-user set lets "delete account" sign out every device, not just this one
    kv.pipeline(["SET", f"{P}sess:{token}", json.dumps(_public(user), separators=(",", ":")), "EX", ttl],
                ["SADD", f"{P}usess:{user['id']}", token],
                ["EXPIRE", f"{P}usess:{user['id']}", ttl])
    return token


def signup(first_name: str, username: str, email: str, password: str) -> tuple[dict, str]:
    a = _auth()
    salt = secrets.token_bytes(16)
    # claim the username, then the email; give the username back if the email is taken
    uid = int(kv.cmd("INCR", P + "uid"))
    if kv.cmd("SET", f"{P}name:{username}", uid, "NX") is None:
        raise a.AuthError("That username is taken.")
    if kv.cmd("SET", f"{P}mail:{email}", uid, "NX") is None:
        kv.cmd("DEL", f"{P}name:{username}")
        raise a.AuthError("An account with that email already exists — log in instead.")
    user = {"id": uid, "username": username, "email": email, "firstName": first_name,
            "ph": a._hash(password, salt).hex(), "salt": salt.hex(), "createdAt": time.time()}
    kv.set_json(f"{P}user:{uid}", user)
    return _public(user), _new_session(user)


def login(ident: str, password: str) -> tuple[dict, str]:
    a = _auth()
    uid = kv.cmd("GET", f"{P}name:{ident}") or kv.cmd("GET", f"{P}mail:{ident}")
    user = kv.get_json(f"{P}user:{uid}") if uid else None
    salt = bytes.fromhex(user["salt"]) if user else b"\0" * 16
    ok = user is not None and hmac.compare_digest(a._hash(password, salt), bytes.fromhex(user["ph"]))
    if not ok:
        raise a.AuthError("Wrong email/username or password.")
    return _public(user), _new_session(user)


def user_for(token: str) -> dict | None:
    # GETEX returns the session and pushes its expiry out again in one command
    raw = kv.cmd("GETEX", f"{P}sess:{token}", "EX", _auth().SESSION_TTL)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def logout(token: str) -> None:
    kv.cmd("DEL", f"{P}sess:{token}")


def count() -> int:
    return int(kv.cmd("GET", P + "uid") or 0)


def clear_data(user_id: int) -> None:
    kv.cmd("DEL", f"{P}state:{user_id}")


def delete_account(user_id: int) -> None:
    user = kv.get_json(f"{P}user:{user_id}") or {}
    tokens = kv.cmd("SMEMBERS", f"{P}usess:{user_id}") or []
    cmds = [["DEL", f"{P}state:{user_id}"], ["DEL", f"{P}user:{user_id}"], ["DEL", f"{P}usess:{user_id}"]]
    if user.get("username"):
        cmds.append(["DEL", f"{P}name:{user['username']}"])
    if user.get("email"):
        cmds.append(["DEL", f"{P}mail:{user['email']}"])
    cmds += [["DEL", f"{P}sess:{t}"] for t in tokens]
    kv.pipeline(*cmds)


def get_state(user_id: int) -> dict:
    st = kv.get_json(f"{P}state:{user_id}") or {}
    return {"favorites": st.get("favorites", []), "hauls": st.get("hauls", []),
            "history": st.get("history", []), "updatedAt": st.get("updatedAt")}


def set_state(user_id: int, favorites: list, hauls: list, history: list) -> dict:
    now = time.time()
    kv.set_json(f"{P}state:{user_id}", {"favorites": favorites, "hauls": hauls, "history": history, "updatedAt": now})
    return {"ok": True, "updatedAt": now}
