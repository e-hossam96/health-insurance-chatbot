"""Tests for step 2.2: auth endpoints (B1, B5, B10, B11)."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app import create_app
from backend.config import Settings

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot",
)


@pytest.fixture()
def app(_migrate_fresh: None) -> object:
    settings = Settings(database_url=TEST_DB_URL)  # type: ignore[call-arg]
    return create_app(settings)


@pytest.fixture()
async def client(app: object) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        yield c  # type: ignore[misc]


async def _signup(client: AsyncClient, username: str = "alice", password: str = "password123") -> object:
    return await client.post(
        "/auth/signup",
        json={"username": username, "password": password},
    )


async def _login(client: AsyncClient, username: str = "alice", password: str = "password123") -> object:
    return await client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )


def _get_cookie(response: object) -> str | None:
    for header_name, header_value in response.headers.multi_items():  # type: ignore[union-attr]
        if header_name.lower() == "set-cookie" and "session_id=" in header_value:
            return header_value
    return None


@pytest.mark.anyio()
async def test_B1_signup_cannot_set_role(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/signup",
        json={"username": "alice", "password": "password123", "role": "admin"},
    )
    assert resp.status_code == 201

    me_resp = await client.get("/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "user"


@pytest.mark.anyio()
async def test_B5_login_case_insensitive(client: AsyncClient) -> None:
    await _signup(client, "Alice")
    resp = await _login(client, "alice")
    assert resp.status_code == 200


@pytest.mark.anyio()
async def test_B10_wrong_user_and_wrong_password_same_message(client: AsyncClient) -> None:
    await _signup(client, "alice")

    resp_wrong_user = await client.post(
        "/auth/login",
        json={"username": "nonexistent", "password": "password123"},
    )
    resp_wrong_pass = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "wrongpassword"},
    )
    assert resp_wrong_user.status_code == 401
    assert resp_wrong_pass.status_code == 401
    assert resp_wrong_user.json() == resp_wrong_pass.json()


@pytest.mark.anyio()
async def test_B10_cookie_flags(client: AsyncClient) -> None:
    resp = await _signup(client)
    cookie = _get_cookie(resp)
    assert cookie is not None
    lower = cookie.lower()
    assert "httponly" in lower
    assert "secure" in lower
    assert "samesite=lax" in lower


@pytest.mark.anyio()
async def test_B10_state_changing_rejects_non_json(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/signup",
        content="username=alice&password=password123",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio()
async def test_B11_user_cannot_set_mode_admin(client: AsyncClient) -> None:
    await _signup(client)
    resp = await client.post(
        "/auth/mode",
        json={"mode": "admin"},
    )
    assert resp.status_code == 403


@pytest.mark.anyio()
async def test_B10_signup_creates_session(client: AsyncClient) -> None:
    resp = await _signup(client)
    assert resp.status_code == 201
    me_resp = await client.get("/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "alice"


@pytest.mark.anyio()
async def test_B10_logout_clears_session(client: AsyncClient) -> None:
    await _signup(client)
    resp = await client.post("/auth/logout", json={})
    assert resp.status_code == 200
    me_resp = await client.get("/auth/me")
    assert me_resp.status_code == 401


@pytest.mark.anyio()
async def test_B1_signup_short_password_rejected(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/signup",
        json={"username": "alice", "password": "short"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio()
async def test_B5_signup_duplicate_username(client: AsyncClient) -> None:
    await _signup(client, "alice")
    resp = await _signup(client, "Alice")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "username_taken"
