from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app import create_app
from backend.config import Settings

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot",
)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        self._now += timedelta(**kwargs)


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC))


@pytest.fixture()
def app(_clean_database: None, clock: FakeClock) -> object:
    settings = Settings(database_url=TEST_DB_URL)  # type: ignore[call-arg]
    application = create_app(settings)
    application.state.clock = clock
    return application


@pytest.fixture()
async def client(app: object) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        yield c  # type: ignore[misc]


@pytest.mark.anyio()
async def test_F15_signup_rate_limit(client: AsyncClient, clock: FakeClock) -> None:
    for i in range(5):
        resp = await client.post(
            "/auth/signup",
            json={"username": f"user{i}", "password": "password123"},
        )
        assert resp.status_code == 201, f"signup {i} failed: {resp.json()}"

    resp = await client.post(
        "/auth/signup",
        json={"username": "user_extra", "password": "password123"},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert resp.json()["detail"]["error"]["code"] == "rate_limited"


@pytest.mark.anyio()
async def test_F15_signup_rate_limit_resets(client: AsyncClient, clock: FakeClock) -> None:
    for i in range(5):
        await client.post(
            "/auth/signup",
            json={"username": f"user{i}", "password": "password123"},
        )

    resp = await client.post(
        "/auth/signup",
        json={"username": "blocked", "password": "password123"},
    )
    assert resp.status_code == 429

    clock.advance(hours=1, seconds=1)

    resp = await client.post(
        "/auth/signup",
        json={"username": "allowed_again", "password": "password123"},
    )
    assert resp.status_code == 201


@pytest.mark.anyio()
async def test_F15_login_fail_rate_limit(client: AsyncClient, clock: FakeClock) -> None:
    await client.post(
        "/auth/signup",
        json={"username": "alice", "password": "password123"},
    )

    for _ in range(10):
        resp = await client.post(
            "/auth/login",
            json={"username": "alice", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    resp = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "wrongpassword"},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


@pytest.mark.anyio()
async def test_F15_login_fail_rate_limit_resets(client: AsyncClient, clock: FakeClock) -> None:
    await client.post(
        "/auth/signup",
        json={"username": "alice", "password": "password123"},
    )

    for _ in range(10):
        await client.post(
            "/auth/login",
            json={"username": "alice", "password": "wrongpassword"},
        )

    resp = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "wrongpassword"},
    )
    assert resp.status_code == 429

    clock.advance(minutes=15, seconds=1)

    resp = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "password123"},
    )
    assert resp.status_code == 200


@pytest.mark.anyio()
async def test_F15_signup_limit_is_per_client_ip_from_proxy_header(client: AsyncClient) -> None:
    first_ip = {"X-Forwarded-For": "203.0.113.1"}
    for i in range(5):
        resp = await client.post("/auth/signup", json={"username": f"a{i}", "password": "password123"}, headers=first_ip)
        assert resp.status_code == 201

    blocked = await client.post("/auth/signup", json={"username": "a_extra", "password": "password123"}, headers=first_ip)
    assert blocked.status_code == 429

    other_ip = await client.post(
        "/auth/signup",
        json={"username": "b0", "password": "password123"},
        headers={"X-Forwarded-For": "198.51.100.7, 10.0.0.1"},
    )
    assert other_ip.status_code == 201


@pytest.mark.anyio()
async def test_F15_login_limit_is_per_ip_and_username(client: AsyncClient) -> None:
    for name in ("alice", "bob"):
        await client.post("/auth/signup", json={"username": name, "password": "password123"})
    attacker = {"X-Forwarded-For": "203.0.113.9"}
    for _ in range(10):
        resp = await client.post("/auth/login", json={"username": "alice", "password": "wrong"}, headers=attacker)
        assert resp.status_code == 401
    blocked = await client.post("/auth/login", json={"username": "alice", "password": "wrong"}, headers=attacker)
    assert blocked.status_code == 429

    other_user_same_ip = await client.post(
        "/auth/login", json={"username": "bob", "password": "password123"}, headers=attacker
    )
    assert other_user_same_ip.status_code == 200

    same_user_other_ip = await client.post(
        "/auth/login", json={"username": "alice", "password": "password123"}, headers={"X-Forwarded-For": "198.51.100.2"}
    )
    assert same_user_other_ip.status_code == 200
