from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from code_index import auth


@pytest.fixture(autouse=True)
def _patch_auth_file(tmp_path):
    orig_dir = auth.AUTH_DIR
    auth.AUTH_DIR = str(tmp_path)
    auth.AUTH_FILE = str(tmp_path / "auth.json")
    yield
    auth.AUTH_DIR = orig_dir
    auth.AUTH_FILE = os.path.join(orig_dir, "auth.json")


class _AuthMiddleware:
    """Replica of cli._AuthMiddleware for testing in isolation."""

    def __init__(self, app, api_key=""):
        self.app = app
        self.api_key = api_key
        self._has_keys = bool(api_key)
        self._has_users = bool(auth.list_users())

    async def __call__(self, scope, receive, send):
        if not self._has_keys and not self._has_users:
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in ("/health", "/favicon.ico"):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        bearer = headers.get(b"authorization", b"").decode().removeprefix("Bearer ")

        if self._has_keys:
            if bearer == self.api_key:
                await self.app(scope, receive, send)
                return
        elif auth.verify(bearer):
            await self.app(scope, receive, send)
            return
        await self._unauthorized(send)

    async def _unauthorized(self, send):
        body = b'{"error":"unauthorized"}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})


async def _ok_app(scope, receive, send):
    body = b"ok"
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"text/plain"), (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body})


@pytest.mark.asyncio
async def test_health_skips_auth():
    mw = _AuthMiddleware(_ok_app)
    _, r = await _request(mw, "GET", "/health")
    assert r["status"] == 200


@pytest.mark.asyncio
async def test_no_auth_configured_allows_all():
    mw = _AuthMiddleware(_ok_app)
    _, r = await _request(mw, "GET", "/sse")
    assert r["status"] == 200


@pytest.mark.asyncio
async def test_valid_key_passes():
    raw = auth.add_user("alice")
    mw = _AuthMiddleware(_ok_app)
    _, r = await _request(mw, "GET", "/sse", headers={"Authorization": f"Bearer {raw}"})
    assert r["status"] == 200


@pytest.mark.asyncio
async def test_invalid_key_rejected():
    auth.add_user("alice")
    mw = _AuthMiddleware(_ok_app)
    _, r = await _request(mw, "GET", "/sse", headers={"Authorization": "Bearer wrongkey"})
    assert r["status"] == 401


@pytest.mark.asyncio
async def test_missing_header_rejected():
    auth.add_user("alice")
    mw = _AuthMiddleware(_ok_app)
    _, r = await _request(mw, "GET", "/sse")
    assert r["status"] == 401


@pytest.mark.asyncio
async def test_legacy_api_key_still_works():
    mw = _AuthMiddleware(_ok_app, api_key="legacy-key")
    _, r = await _request(mw, "GET", "/sse", headers={"Authorization": "Bearer legacy-key"})
    assert r["status"] == 200


@pytest.mark.asyncio
async def test_legacy_key_ignores_auth_file():
    raw = auth.add_user("bob")
    mw = _AuthMiddleware(_ok_app, api_key="legacy-key")
    _, r = await _request(mw, "GET", "/sse", headers={"Authorization": f"Bearer {raw}"})
    assert r["status"] == 401


@pytest.mark.asyncio
async def test_legacy_key_wrong_rejected():
    mw = _AuthMiddleware(_ok_app, api_key="legacy-key")
    _, r = await _request(mw, "GET", "/sse", headers={"Authorization": "Bearer wrong-key"})
    assert r["status"] == 401


@pytest.mark.asyncio
async def test_favicon_skips_auth():
    auth.add_user("alice")
    mw = _AuthMiddleware(_ok_app)
    _, r = await _request(mw, "GET", "/favicon.ico")
    assert r["status"] == 200


@pytest.mark.asyncio
async def test_auth_response_body():
    auth.add_user("alice")
    mw = _AuthMiddleware(_ok_app)
    body, r = await _request(mw, "GET", "/sse")
    assert body == b'{"error":"unauthorized"}'
    headers = dict(r.get("headers", []))
    assert headers.get(b"content-type") == b"application/json"


async def _request(mw, method, path, headers=None):
    body = b""
    response_start = {}
    response_body = b""

    async def send(event):
        nonlocal response_start, response_body
        if event["type"] == "http.response.start":
            response_start = event
        elif event["type"] == "http.response.body":
            response_body += event.get("body", b"")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    h = [(b"authorization", headers["Authorization"].encode())] if headers else []
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": h,
        "query_string": b"",
    }
    await mw(scope, receive, send)
    return response_body, response_start
