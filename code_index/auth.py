from __future__ import annotations

import hashlib
import json
import os
import secrets
import time

AUTH_DIR = os.path.expanduser("~/.config/code_index")
AUTH_FILE = os.path.join(AUTH_DIR, "auth.json")
KEY_PREFIX = "cik_"


def _ensure_dir():
    os.makedirs(AUTH_DIR, exist_ok=True)


def _load_users() -> dict:
    if not os.path.exists(AUTH_FILE):
        return {}
    with open(AUTH_FILE) as f:
        return json.load(f)


def _save_users(users: dict):
    _ensure_dir()
    with open(AUTH_FILE, "w") as f:
        json.dump(users, f, indent=2)


def _hash_key(raw_key: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", raw_key.encode(), salt.encode(), 100000)
    return h.hex(), salt


def generate_key() -> tuple[str, str]:
    """Generate a raw API key. Returns (raw_key, key_id).
    The key_id is the first 12 chars of the raw key (prefix + 8 hex chars)."""
    raw = KEY_PREFIX + secrets.token_hex(32)
    return raw, raw[:12]


def add_user(name: str) -> str:
    """Create a new API key for a user. Returns the raw key (show once)."""
    raw, key_id = generate_key()
    h, salt = _hash_key(raw)
    users = _load_users()
    users[name] = {
        "hash": h,
        "salt": salt,
        "key_id": key_id,
        "created_at": time.time(),
    }
    _save_users(users)
    return raw


def verify(token: str) -> str | None:
    """Check a Bearer token against stored hashes. Returns the username or None."""
    if not token:
        return None
    users = _load_users()
    if not users:
        return None
    for name, data in users.items():
        h, _ = _hash_key(token, data["salt"])
        if h == data["hash"]:
            return name
    return None


def list_users() -> list[dict]:
    users = _load_users()
    return [
        {
            "name": name,
            "key_id": data["key_id"],
            "created_at": data["created_at"],
        }
        for name, data in users.items()
    ]


def revoke_user(name: str | None = None, key_id: str | None = None) -> bool:
    users = _load_users()
    if name:
        if name in users:
            del users[name]
            _save_users(users)
            return True
        return False
    if key_id:
        for n, data in list(users.items()):
            if data.get("key_id") == key_id:
                del users[n]
                _save_users(users)
                return True
        return False
    return False
