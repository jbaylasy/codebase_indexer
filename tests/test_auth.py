from __future__ import annotations

import json
import os

import pytest

from code_index import auth


@pytest.fixture(autouse=True)
def _patch_auth_file(tmp_path):
    """Redirect auth storage to a temp dir so tests don't touch ~/.config."""
    orig = auth.AUTH_DIR
    auth.AUTH_DIR = str(tmp_path)
    auth.AUTH_FILE = str(tmp_path / "auth.json")
    yield
    auth.AUTH_DIR = orig
    auth.AUTH_FILE = os.path.join(orig, "auth.json")


def test_generate_key_format():
    raw, key_id = auth.generate_key()
    assert raw.startswith("cik_")
    assert len(raw) == 4 + 64
    assert key_id == raw[:12]


def test_generate_key_unique():
    keys = {auth.generate_key()[0] for _ in range(100)}
    assert len(keys) == 100


def test_hash_key_deterministic():
    h1, salt = auth._hash_key("hello")
    h2, _ = auth._hash_key("hello", salt)
    assert h1 == h2


def test_hash_key_different_salts():
    h1, _ = auth._hash_key("hello")
    h2, _ = auth._hash_key("hello")
    assert h1 != h2


def test_add_user_returns_key():
    raw = auth.add_user("alice")
    assert raw.startswith("cik_")
    assert len(raw) == 4 + 64


def test_add_user_stores_hash():
    raw = auth.add_user("alice")
    data = json.load(open(auth.AUTH_FILE))
    assert "alice" in data
    entry = data["alice"]
    assert entry["key_id"] == raw[:12]
    assert "hash" in entry
    assert "salt" in entry
    assert "created_at" in entry


def test_verify_valid_token():
    raw = auth.add_user("bob")
    assert auth.verify(raw) == "bob"


def test_verify_wrong_token():
    auth.add_user("bob")
    assert auth.verify("cik_" + "a" * 64) is None


def test_verify_empty():
    auth.add_user("bob")
    assert auth.verify("") is None
    assert auth.verify(None) is None


def test_verify_no_users():
    assert auth.verify("cik_" + "a" * 64) is None


def test_verify_after_revoke():
    raw = auth.add_user("charlie")
    auth.revoke_user(name="charlie")
    assert auth.verify(raw) is None


def test_list_users_empty():
    assert auth.list_users() == []


def test_list_users():
    auth.add_user("alice")
    auth.add_user("bob")
    users = {u["name"] for u in auth.list_users()}
    assert users == {"alice", "bob"}


def test_list_users_does_not_expose_hash():
    auth.add_user("alice")
    users = auth.list_users()
    assert "hash" not in users[0]
    assert "salt" not in users[0]


def test_revoke_by_name():
    auth.add_user("alice")
    assert auth.revoke_user(name="alice") is True
    assert auth.list_users() == []


def test_revoke_by_key_id():
    raw = auth.add_user("alice")
    kid = raw[:12]
    assert auth.revoke_user(key_id=kid) is True
    assert auth.list_users() == []


def test_revoke_nonexistent_user():
    assert auth.revoke_user(name="nobody") is False


def test_revoke_nonexistent_key_id():
    assert auth.revoke_user(key_id="cik_nonexist") is False


def test_revoke_no_args():
    assert auth.revoke_user() is False


def test_multiple_users_persistence():
    auth.add_user("alice")
    auth.add_user("bob")
    raw = auth.add_user("charlie")
    assert auth.verify(raw) == "charlie"
    auth.revoke_user(name="alice")
    assert len(auth.list_users()) == 2
