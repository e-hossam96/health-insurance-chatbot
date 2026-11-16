from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from backend_routes import all_routes
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings

TEST_DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot"
)
PUBLIC_ROUTES = {
    ("POST", "/auth/signup"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("GET", "/auth/me"),
    ("POST", "/auth/mode"),
    ("GET", "/locations"),
    ("GET", "/health"),
}
RAW_BODY_ROUTES = {("POST", "/admin/kb-documents")}


def _routes(app: FastAPI) -> set[tuple[str, str]]:
    routes = all_routes(app)
    assert routes >= {
        (m.upper(), p) for p, ms in app.openapi()["paths"].items() for m in ms
    }
    return routes


@pytest.fixture()
def app(_migrate_fresh: None) -> FastAPI:
    return create_app(Settings(database_url=TEST_DB_URL), ai_from_env=False)  # type: ignore[call-arg]


@pytest.fixture()
async def user(app: FastAPI) -> AsyncIterator[AsyncClient]:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        await client.post(
            "/auth/signup", json={"username": "mona", "password": "monapass1"}
        )
        await client.post(
            "/auth/login", json={"username": "mona", "password": "monapass1"}
        )
        locations = (await client.get("/locations")).json()
        await client.post(
            "/me/profile", json={"name": "Mona", "location_id": locations[0]["id"]}
        )
        yield client


def test_B8_every_route_is_role_guarded_by_prefix_or_explicitly_public(
    app: FastAPI,
) -> None:
    unguarded = {
        (m, p) for m, p in _routes(app) if not p.startswith(("/admin/", "/me/"))
    }
    assert unguarded == PUBLIC_ROUTES, (
        f"routes outside /admin and /me must be listed as public: {sorted(unguarded - PUBLIC_ROUTES)}"
    )


@pytest.mark.anyio()
async def test_B8_session_routes_outside_the_prefixes_still_need_a_login(
    app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as anon:
        assert (await anon.get("/auth/me")).status_code == 401
        assert (await anon.post("/auth/mode", json={"mode": "user"})).status_code == 401


@pytest.mark.anyio()
async def test_B10_every_state_changing_route_accepts_json_only(
    app: FastAPI, user: AsyncClient
) -> None:
    writes = sorted(
        (m, p)
        for m, p in _routes(app)
        if m in {"POST", "PUT", "PATCH", "DELETE"} and (m, p) not in RAW_BODY_ROUTES
    )
    assert len(writes) > 10
    for method, path in writes:
        concrete = path.replace("{", "").replace("}", "")
        for content_type in ("text/plain", "application/x-www-form-urlencoded"):
            response = await user.request(
                method,
                concrete.replace("_id", "1"),
                content=b'{"a": 1}',
                headers={"content-type": content_type},
            )
            assert response.status_code == 422, (
                f"{method} {path} accepted {content_type}"
            )
            assert response.json()["detail"]["error"]["code"] == "validation_error"


@pytest.mark.anyio()
async def test_B10_a_text_plain_booking_changes_nothing(
    user: AsyncClient, db_engine: Engine
) -> None:
    response = await user.post(
        "/me/visits",
        content=b'{"session_id": 1, "slot_id": 1}',
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == 422
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM visit")).scalar_one() == 0


@pytest.mark.anyio()
async def test_B8_errors_do_not_leak_ids_or_internals(
    app: FastAPI, user: AsyncClient
) -> None:
    for method, path, body in (
        ("POST", "/me/visits/987654/cancel", {"session_id": None}),
        ("GET", "/me/sessions/987654/messages", None),
        ("POST", "/me/chat", {"session_id": 987654, "message": "hi"}),
    ):
        response = await user.request(method, path, json=body)
        assert response.status_code == 404, path
        assert "987654" not in response.text, f"{path} echoes the id"
        assert response.json()["detail"]["error"]["code"] == "not_found"

    async def explode() -> None:
        raise RuntimeError("secret internal detail 4242")

    app.add_api_route("/me/boom", explode, methods=["GET"])
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://test",
    ) as client:
        client.cookies = user.cookies
        crashed = await client.get("/me/boom")
    assert crashed.status_code == 500
    assert (
        "secret" not in crashed.text
        and "Traceback" not in crashed.text
        and "4242" not in crashed.text
    )


@pytest.mark.anyio()
async def test_B10_bodyless_writes_reject_form_multipart_and_text_content_types(
    app: FastAPI, user: AsyncClient
) -> None:
    writes = sorted(
        (m, p)
        for m, p in _routes(app)
        if m in {"POST", "PUT", "PATCH", "DELETE"} and (m, p) not in RAW_BODY_ROUTES
    )
    for method, path in writes:
        concrete = path.replace("{", "").replace("}", "").replace("_id", "1")
        for content_type in (
            "text/plain",
            "application/x-www-form-urlencoded",
            "multipart/form-data; boundary=x",
        ):
            response = await user.request(
                method, concrete, content=b"", headers={"content-type": content_type}
            )
            assert response.status_code == 422, (
                f"{method} {path} accepted an empty {content_type} body"
            )


@pytest.mark.anyio()
async def test_B10_an_empty_cross_site_form_post_cannot_log_a_member_out(
    user: AsyncClient,
) -> None:
    response = await user.post(
        "/auth/logout",
        content=b"",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 422
    assert (await user.get("/auth/me")).status_code == 200


@pytest.mark.anyio()
async def test_B8_the_api_docs_and_schema_are_not_served(app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as anon:
        for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
            assert (await anon.get(path)).status_code == 404, path
