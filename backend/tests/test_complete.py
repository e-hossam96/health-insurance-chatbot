"""Tests for step 4.3: Complete visit (D3)."""

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
def app(_migrate_fresh: None) -> object:
    settings = Settings(database_url=TEST_DB_URL)  # type: ignore[call-arg]
    return create_app(settings)


@pytest.fixture()
async def admin_client(app: object) -> AsyncClient:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "DefaultLoc")
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
        yield c  # type: ignore[misc]


def _setup_visit(db_engine: Engine, status: str = "scheduled") -> int:
    """Create a visit with the given status, return visit_id."""
    with db_engine.connect() as conn:
        loc_id = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        clinic_id = conn.execute(
            text("INSERT INTO clinic (name, location_id) VALUES ('C', :l) RETURNING id"), {"l": loc_id}
        ).scalar_one()
        spec_id = conn.execute(text("INSERT INTO specialty (name) VALUES ('S') RETURNING id")).scalar_one()
        cs_id = conn.execute(
            text("INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s) RETURNING id"),
            {"c": clinic_id, "s": spec_id},
        ).scalar_one()
        doctor_id = conn.execute(
            text("INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr', :cs) RETURNING id"),
            {"cs": cs_id},
        ).scalar_one()
        slot_status = "booked" if status == "scheduled" else "available"
        slot_id = conn.execute(
            text(f"INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-15 10:00:00+00', '{slot_status}') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        profile_id = conn.execute(text("SELECT id FROM profile LIMIT 1")).scalar_one()
        visit_id = conn.execute(
            text(f"INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, '{status}') RETURNING id"),
            {"p": profile_id, "s": slot_id},
        ).scalar_one()
        conn.commit()
    return visit_id


@pytest.mark.anyio()
async def test_D3_complete_scheduled_visit(
    admin_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_visit(db_engine, "scheduled")
    resp = await admin_client.post(f"/admin/visits/{visit_id}/complete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.anyio()
async def test_D3_completed_is_final(
    admin_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_visit(db_engine, "completed")
    resp = await admin_client.post(f"/admin/visits/{visit_id}/complete")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "invalid_transition"


@pytest.mark.anyio()
async def test_D3_cancelled_is_final(
    admin_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_visit(db_engine, "cancelled")
    resp = await admin_client.post(f"/admin/visits/{visit_id}/complete")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "invalid_transition"


@pytest.mark.anyio()
async def test_D3_user_cannot_complete(app: object, db_engine: Engine) -> None:
    """D3: non-admin user gets 403 on the complete endpoint."""
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "DefaultLoc")

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/signup", json={"username": "user1", "password": "userpass1"})
        await c.post("/auth/login", json={"username": "user1", "password": "userpass1"})
        locs = (await c.get("/locations")).json()
        await c.post("/me/profile", json={"name": "Test User", "location_id": locs[0]["id"]})

    visit_id = _setup_visit(db_engine, "scheduled")

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/login", json={"username": "user1", "password": "userpass1"})
        resp = await c.post(f"/admin/visits/{visit_id}/complete")
    assert resp.status_code == 403
