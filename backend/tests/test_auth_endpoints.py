from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from backend.app import create_app
from backend.config import Settings

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot",
)


@pytest.fixture()
def app(_clean_database: None) -> object:
    settings = Settings(database_url=TEST_DB_URL)  # type: ignore[call-arg]
    return create_app(settings)


@pytest.fixture()
async def client(app: object) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        yield c  # type: ignore[misc]


async def _signup(
    client: AsyncClient, username: str = "alice", password: str = "password123"
) -> object:
    return await client.post(
        "/auth/signup",
        json={"username": username, "password": password},
    )


async def _login(
    client: AsyncClient, username: str = "alice", password: str = "password123"
) -> object:
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
async def test_B10_wrong_user_and_wrong_password_same_message(
    client: AsyncClient,
) -> None:
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
@pytest.mark.parametrize("entry", ["signup", "login"])
async def test_B10_cookie_flags(client: AsyncClient, entry: str) -> None:
    resp = await _signup(client)
    if entry == "login":
        await client.post("/auth/logout", json={})
        resp = await _login(client)
    cookie = _get_cookie(resp)
    assert cookie is not None, f"{entry} sets no session cookie"
    parsed = SimpleCookie()
    parsed.load(cookie)
    morsel = parsed["session_id"]
    assert morsel["httponly"] is True
    assert morsel["secure"] is True
    assert morsel["samesite"].lower() == "lax"
    assert morsel["path"] == "/"
    assert int(morsel["max-age"]) == 7 * 86400


@pytest.mark.anyio()
async def test_B12_the_stored_session_expires_seven_days_after_creation(
    client: AsyncClient,
) -> None:
    await _signup(client)
    engine = create_engine(TEST_DB_URL.replace("+asyncpg", "+psycopg2"))
    with engine.connect() as conn:
        created_at, expires_at = conn.execute(
            text("SELECT created_at, expires_at FROM auth_session")
        ).one()
    engine.dispose()
    assert expires_at - created_at == timedelta(days=7)


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
    resp = await _signup(client)
    old_cookie = _get_cookie(resp)
    assert old_cookie is not None
    token = old_cookie.split(";", 1)[0].split("=", 1)[1]
    resp = await client.post("/auth/logout", json={})
    assert resp.status_code == 200
    client.cookies.clear()
    replay = await client.get("/auth/me", headers={"cookie": f"session_id={token}"})
    assert replay.status_code == 401, (
        "the server must delete the session, not just ask the browser to drop the cookie"
    )
    engine = create_engine(TEST_DB_URL.replace("+asyncpg", "+psycopg2"))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM auth_session")).scalar_one() == 0
    engine.dispose()


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


class MovableClock:
    def __init__(self, at: datetime) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at


@pytest.mark.anyio()
async def test_B12_a_session_works_until_seven_days_and_not_after(
    app: object, client: AsyncClient
) -> None:
    start = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
    clock = MovableClock(start)
    app.state.clock = clock  # type: ignore[attr-defined]
    await _signup(client)
    clock.at = start + timedelta(days=7) - timedelta(seconds=1)
    assert (await client.get("/auth/me")).status_code == 200
    clock.at = start + timedelta(days=7) + timedelta(seconds=1)
    assert (await client.get("/auth/me")).status_code == 401


@pytest.mark.anyio()
async def test_B10_expired_sessions_are_purged_on_startup(
    app: object, client: AsyncClient
) -> None:
    await _signup(client)
    await _signup(client, username="bob")
    engine = create_engine(TEST_DB_URL.replace("+asyncpg", "+psycopg2"))
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE auth_session SET expires_at = now() - interval '1 day', created_at = now() - interval '8 days' "
                "WHERE account_id = (SELECT id FROM account WHERE username = 'alice')"
            )
        )
    async with app.router.lifespan_context(app):  # type: ignore[attr-defined]
        with engine.connect() as conn:
            remaining = (
                conn.execute(
                    text(
                        "SELECT a.username FROM auth_session s JOIN account a ON a.id = s.account_id"
                    )
                )
                .scalars()
                .all()
            )
    engine.dispose()
    assert remaining == ["bob"]
