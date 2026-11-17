from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

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


@pytest.mark.anyio()
async def test_B6_profile_comes_from_session(client: AsyncClient, db_engine: Engine) -> None:
    await client.post(
        "/auth/signup",
        json={"username": "alice", "password": "password123"},
    )
    with db_engine.connect() as conn:
        conn.execute(text("INSERT INTO location (name) VALUES ('Cairo')"))
        conn.commit()

    resp = await client.post(
        "/me/profile",
        json={"name": "Alice", "location_id": 1, "account_id": 9999},
    )
    assert resp.status_code == 201
    data = resp.json()
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT account_id FROM profile WHERE id = :p"),
            {"p": data["id"]},
        ).fetchone()
        assert row is not None
        assert row[0] != 9999


@pytest.mark.anyio()
async def test_B10_login_purges_expired(client: AsyncClient, db_engine: Engine) -> None:
    await client.post(
        "/auth/signup",
        json={"username": "alice", "password": "password123"},
    )
    with db_engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO auth_session (id, account_id, active_mode, expires_at) "
                "VALUES ('expired_hash', "
                "(SELECT id FROM account WHERE username = 'alice'), "
                "'user', '2020-01-01 00:00:00+00')"
            )
        )
        conn.commit()
        count = conn.execute(text("SELECT count(*) FROM auth_session")).scalar()
        assert count is not None
        assert count >= 2

    await client.post(
        "/auth/login",
        json={"username": "alice", "password": "password123"},
    )
    with db_engine.connect() as conn:
        expired = conn.execute(
            text("SELECT count(*) FROM auth_session WHERE id = 'expired_hash'")
        ).scalar()
        assert expired == 0


@pytest.mark.anyio()
async def test_B12_signup_stores_argon2(client: AsyncClient, db_engine: Engine) -> None:
    await client.post(
        "/auth/signup",
        json={"username": "alice", "password": "password123"},
    )
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT password_hash FROM account WHERE username = 'alice'")
        ).fetchone()
        assert row is not None
        assert row[0].startswith("$argon2")
        assert "password123" not in row[0]
