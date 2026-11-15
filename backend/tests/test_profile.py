"""Tests for step 2.4: profile (B2, B3, B4, B9)."""

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


async def _signup(client: AsyncClient, username: str = "user1") -> None:
    await client.post(
        "/auth/signup",
        json={"username": username, "password": "password123"},
    )


async def _seed_location(client: AsyncClient) -> int:
    from sqlalchemy import create_engine, text

    sync_url = TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    engine = create_engine(sync_url)
    with engine.begin() as conn:
        row = conn.execute(
            text("INSERT INTO location (name) VALUES ('Cairo') RETURNING id")
        )
        loc_id: int = row.scalar_one()
    engine.dispose()
    return loc_id


@pytest.mark.anyio()
async def test_B3_create_profile(client: AsyncClient) -> None:
    await _signup(client)
    loc_id = await _seed_location(client)
    resp = await client.post(
        "/me/profile",
        json={"name": "Alice Smith", "location_id": loc_id},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Alice Smith"
    assert data["location_name"] == "Cairo"


@pytest.mark.anyio()
async def test_B4_one_profile_per_account(client: AsyncClient) -> None:
    await _signup(client)
    loc_id = await _seed_location(client)
    resp1 = await client.post(
        "/me/profile",
        json={"name": "Alice", "location_id": loc_id},
    )
    assert resp1.status_code == 201
    resp2 = await client.post(
        "/me/profile",
        json={"name": "Alice Updated", "location_id": loc_id},
    )
    assert resp2.status_code == 409


@pytest.mark.anyio()
async def test_B3_location_must_exist(client: AsyncClient) -> None:
    await _signup(client)
    resp = await client.post(
        "/me/profile",
        json={"name": "Alice", "location_id": 99999},
    )
    assert resp.status_code == 404


@pytest.mark.anyio()
async def test_B4_no_update_or_delete_profile(app: object) -> None:
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    schema = app.openapi()
    paths = schema.get("paths", {})
    profile_path = paths.get("/me/profile", {})
    assert "put" not in profile_path
    assert "patch" not in profile_path
    assert "delete" not in profile_path


@pytest.mark.anyio()
async def test_B2_admin_has_profile(client: AsyncClient) -> None:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    await client.post(
        "/auth/login",
        json={"username": "admin1", "password": "adminpass1"},
    )
    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["has_profile"] is True


@pytest.mark.anyio()
async def test_B9_no_password_reset_route(app: object) -> None:
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    schema = app.openapi()
    paths = schema.get("paths", {})
    for path in paths:
        assert "reset" not in path.lower(), f"Found password reset route: {path}"


@pytest.mark.anyio()
async def test_B3_get_locations(client: AsyncClient) -> None:
    await _seed_location(client)
    resp = await client.get("/locations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["name"] == "Cairo"
