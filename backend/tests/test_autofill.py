from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
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


def _make_app(fake_now: datetime, migrate: None) -> FastAPI:
    settings = Settings(database_url=TEST_DB_URL)  # type: ignore[call-arg]
    application = create_app(settings)
    application.state.clock = FakeClock(fake_now)
    return application


async def _make_admin_client(app: FastAPI) -> AsyncClient:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "DefaultLoc")
    client = AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    )
    await client.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
    return client


async def _setup_doctor(client: AsyncClient) -> int:
    loc = await client.post("/admin/locations", json={"name": "TestCity"})
    loc_id = loc.json()["id"]
    clinic = await client.post("/admin/clinics", json={"name": "Clinic A", "location_id": loc_id})
    clinic_id = clinic.json()["id"]
    spec = await client.post("/admin/specialties", json={"name": "Derm"})
    spec_id = spec.json()["id"]
    cs_list = (
        await client.put(
            f"/admin/clinics/{clinic_id}/specialties",
            json=[{"specialty_id": spec_id}],
        )
    ).json()
    cs_id = cs_list[0]["id"]
    doc = await client.post("/admin/doctors", json={"name": "Dr X", "clinic_specialty_id": cs_id})
    return doc.json()["id"]


@pytest.mark.anyio()
async def test_C5_autofill_expected_counts(_migrate_fresh: None) -> None:
    app = _make_app(datetime(2026, 12, 1, 0, 0, tzinfo=UTC), _migrate_fresh)
    client = await _make_admin_client(app)
    doctor_id = await _setup_doctor(client)

    resp = await client.post("/admin/slots/autofill", json={"doctor_id": doctor_id})
    assert resp.status_code == 200
    assert resp.json()["created"] == 31 * 8
    await client.aclose()


@pytest.mark.anyio()
async def test_C5_autofill_skips_past_hours(_migrate_fresh: None) -> None:
    app = _make_app(datetime(2026, 12, 15, 12, 0, tzinfo=UTC), _migrate_fresh)
    client = await _make_admin_client(app)
    doctor_id = await _setup_doctor(client)

    resp = await client.post("/admin/slots/autofill", json={"doctor_id": doctor_id})
    assert resp.status_code == 200
    remaining_days = 31 - 15  # Dec 16-31: 16 full days
    today_slots = 5  # hours 12,13,14,15,16
    expected = today_slots + remaining_days * 8
    assert resp.json()["created"] == expected
    await client.aclose()


@pytest.mark.anyio()
async def test_C5_autofill_idempotent(_migrate_fresh: None) -> None:
    app = _make_app(datetime(2026, 12, 1, 0, 0, tzinfo=UTC), _migrate_fresh)
    client = await _make_admin_client(app)
    doctor_id = await _setup_doctor(client)

    resp1 = await client.post("/admin/slots/autofill", json={"doctor_id": doctor_id})
    assert resp1.json()["created"] > 0

    resp2 = await client.post("/admin/slots/autofill", json={"doctor_id": doctor_id})
    assert resp2.json()["created"] == 0
    await client.aclose()


@pytest.mark.anyio()
async def test_C5_autofill_current_month_only_last_day(_migrate_fresh: None) -> None:
    app = _make_app(datetime(2026, 12, 31, 0, 0, tzinfo=UTC), _migrate_fresh)
    client = await _make_admin_client(app)
    doctor_id = await _setup_doctor(client)

    resp = await client.post("/admin/slots/autofill", json={"doctor_id": doctor_id})
    assert resp.status_code == 200
    assert resp.json()["created"] == 8
    await client.aclose()


@pytest.mark.anyio()
async def test_C5_autofill_nothing_to_create(_migrate_fresh: None) -> None:
    app = _make_app(datetime(2026, 12, 31, 17, 30, tzinfo=UTC), _migrate_fresh)
    client = await _make_admin_client(app)
    doctor_id = await _setup_doctor(client)

    resp = await client.post("/admin/slots/autofill", json={"doctor_id": doctor_id})
    assert resp.status_code == 200
    assert resp.json()["created"] == 0
    assert resp.json()["message"] == "Nothing to create"
    await client.aclose()


@pytest.mark.anyio()
async def test_C5_autofill_nonexistent_doctor(_migrate_fresh: None) -> None:
    app = _make_app(datetime(2026, 12, 1, 0, 0, tzinfo=UTC), _migrate_fresh)
    client = await _make_admin_client(app)

    resp = await client.post("/admin/slots/autofill", json={"doctor_id": 99999})
    assert resp.status_code == 404
    await client.aclose()
