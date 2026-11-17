from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
from backend_routes import all_routes
from httpx import ASGITransport, AsyncClient

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
async def client(app: object) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        yield c


def _get_protected_routes(app: object) -> list[tuple[str, str]]:
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    return sorted((m, p) for m, p in all_routes(app) if p.startswith(("/admin/", "/me/")))


def _admin_routes(app: object) -> list[tuple[str, str]]:
    return [(m, p) for m, p in _get_protected_routes(app) if p.startswith("/admin/")]


def _me_routes(app: object) -> list[tuple[str, str]]:
    return [(m, p) for m, p in _get_protected_routes(app) if p.startswith("/me/")]


async def _signup_user(client: AsyncClient, username: str = "user1") -> None:
    await client.post(
        "/auth/signup",
        json={"username": username, "password": "password123"},
    )


async def _create_admin_and_login(client: AsyncClient) -> None:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    await client.post(
        "/auth/login",
        json={"username": "admin1", "password": "adminpass1"},
    )


async def _complete_profile(client: AsyncClient) -> None:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    locations = (await client.get("/locations")).json()
    response = await client.post("/me/profile", json={"name": "Test Person", "location_id": locations[0]["id"]})
    assert response.status_code in (200, 201), response.text


REQUIRED_QUERY = {"/admin/slots": "?doctor_id=1&year=2026&month=12"}


async def _assert_reachable(client: AsyncClient, routes: list[tuple[str, str]]) -> None:
    for method, path in routes:
        resp = await client.request(method, path + (REQUIRED_QUERY.get(path, "") if method == "GET" else ""))
        assert resp.status_code not in (401, 403), f"{method} {path} refused an allowed role: {resp.status_code}"
        if method == "GET" and "{" not in path:
            assert resp.status_code == 200, f"GET {path} should be served to an allowed role, got {resp.status_code}"


@pytest.mark.anyio()
async def test_B11_admin_in_user_mode_can_access_me_routes(app: object, client: AsyncClient) -> None:
    await _create_admin_and_login(client)
    assert (await client.post("/auth/mode", json={"mode": "user"})).status_code == 200
    await _assert_reachable(client, _me_routes(app))


@pytest.mark.anyio()
async def test_B8_protected_routes_exist(app: object) -> None:
    assert len(_admin_routes(app)) > 0, "No /admin/ routes found"
    assert len(_me_routes(app)) > 0, "No /me/ routes found"


@pytest.mark.anyio()
async def test_B8_unauthenticated_gets_401(app: object, client: AsyncClient) -> None:
    for method, path in _get_protected_routes(app):
        resp = await client.request(method, path)
        assert resp.status_code == 401, f"{method} {path} should return 401 unauthenticated"


@pytest.mark.anyio()
async def test_B11_user_cannot_access_admin_routes(app: object, client: AsyncClient) -> None:
    await _signup_user(client)
    for method, path in _admin_routes(app):
        resp = await client.request(method, path)
        assert resp.status_code == 403, f"{method} {path} should return 403 for user"


@pytest.mark.anyio()
async def test_B11_admin_in_user_mode_cannot_access_admin_routes(
    app: object, client: AsyncClient
) -> None:
    await _create_admin_and_login(client)
    await client.post("/auth/mode", json={"mode": "user"})
    for method, path in _admin_routes(app):
        resp = await client.request(method, path)
        assert resp.status_code == 403, f"{method} {path} should return 403 for admin in user mode"


@pytest.mark.anyio()
async def test_B11_admin_in_admin_mode_can_access_admin_routes(
    app: object, client: AsyncClient
) -> None:
    await _create_admin_and_login(client)
    await _assert_reachable(client, _admin_routes(app))


@pytest.mark.anyio()
async def test_B11_admin_in_admin_mode_cannot_access_me_routes(
    app: object, client: AsyncClient
) -> None:
    await _create_admin_and_login(client)
    for method, path in _me_routes(app):
        resp = await client.request(method, path)
        assert resp.status_code == 403, f"{method} {path} should return 403 for admin mode"


@pytest.mark.anyio()
async def test_B11_user_can_access_me_routes(
    app: object, client: AsyncClient
) -> None:
    await _signup_user(client)
    await _complete_profile(client)
    await _assert_reachable(client, _me_routes(app))
