"""Tests for step 2.3: authorization (B8, B11).

The parametrized matrix is generated from the app's registered routes,
so adding a new /admin/* or /me/* route without proper guards will fail here.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

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
async def client(app: object) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        yield c


def _get_protected_routes(app: object) -> list[tuple[str, str]]:
    """Extract all routes starting with /admin/ or /me/ from the OpenAPI schema."""
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)
    schema = app.openapi()
    routes: list[tuple[str, str]] = []
    for path, methods in schema.get("paths", {}).items():
        if path.startswith(("/admin/", "/me/")):
            for method in methods:
                if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    routes.append((method.upper(), path))
    return sorted(routes)


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


@pytest.mark.anyio()
async def test_B8_protected_routes_exist(app: object) -> None:
    """Sanity check that we have at least one admin and one me route."""
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
    for method, path in _admin_routes(app):
        resp = await client.request(method, path)
        assert resp.status_code != 401, f"{method} {path} should not return 401"
        assert resp.status_code != 403, f"{method} {path} should not return 403"


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
    for method, path in _me_routes(app):
        resp = await client.request(method, path)
        assert resp.status_code != 401, f"{method} {path} should not return 401"
        assert resp.status_code != 403, f"{method} {path} should not return 403"
