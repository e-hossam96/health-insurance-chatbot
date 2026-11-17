from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings, get_settings

TEST_DB_URL = get_settings().database_url


@pytest.fixture()
def app(_clean_database: None) -> object:
    settings = Settings()  # type: ignore[call-arg]
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


async def _setup_doctor(client: AsyncClient) -> tuple[int, int]:
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
    doctor_id = doc.json()["id"]
    return doctor_id, cs_id


# --- C1: on the hour ---


@pytest.mark.anyio()
async def test_C1_slot_must_be_on_the_hour(admin_client: AsyncClient) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    resp = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T10:30:00Z"},
    )
    assert resp.status_code == 422
    assert "on the hour" in resp.json()["detail"]["error"]["message"].lower()


# --- C2: working day 9-16 UTC ---


@pytest.mark.anyio()
async def test_C2_slot_before_9_rejected(admin_client: AsyncClient) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    resp = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T08:00:00Z"},
    )
    assert resp.status_code == 422
    assert "working" in resp.json()["detail"]["error"]["message"].lower()


@pytest.mark.anyio()
async def test_C2_slot_at_17_rejected(admin_client: AsyncClient) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    resp = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T17:00:00Z"},
    )
    assert resp.status_code == 422
    assert "working" in resp.json()["detail"]["error"]["message"].lower()


@pytest.mark.anyio()
async def test_C2_slot_at_9_accepted(admin_client: AsyncClient) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    resp = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T09:00:00Z"},
    )
    assert resp.status_code == 201
    assert resp.json()["doctor_id"] == doctor_id


@pytest.mark.anyio()
async def test_C2_slot_at_16_accepted(admin_client: AsyncClient) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    resp = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T16:00:00Z"},
    )
    assert resp.status_code == 201


# --- C3: manual add doctor + date + hour ---


@pytest.mark.anyio()
async def test_C3_add_slot_success(admin_client: AsyncClient) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    resp = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T10:00:00Z"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["doctor_id"] == doctor_id
    assert data["status"] == "available"
    assert "id" in data


@pytest.mark.anyio()
async def test_C3_duplicate_slot_rejected(admin_client: AsyncClient) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T10:00:00Z"},
    )
    resp2 = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T10:00:00Z"},
    )
    assert resp2.status_code == 409
    assert "duplicate" in resp2.json()["detail"]["error"]["message"].lower()


@pytest.mark.anyio()
async def test_C3_slot_nonexistent_doctor(admin_client: AsyncClient) -> None:
    resp = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": 99999, "start_at": "2026-12-01T10:00:00Z"},
    )
    assert resp.status_code == 404


# --- C4: manual remove, only while available ---


@pytest.mark.anyio()
async def test_C4_remove_available_slot(admin_client: AsyncClient) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    create_resp = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T10:00:00Z"},
    )
    slot_id = create_resp.json()["id"]
    del_resp = await admin_client.delete(f"/admin/slots/{slot_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True


@pytest.mark.anyio()
async def test_C4_remove_booked_slot_rejected(
    admin_client: AsyncClient, db_engine: Engine
) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    create_resp = await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T10:00:00Z"},
    )
    slot_id = create_resp.json()["id"]

    with db_engine.connect() as conn:
        conn.execute(
            text("UPDATE slot SET status = 'booked' WHERE id = :s"), {"s": slot_id}
        )
        conn.commit()

    del_resp = await admin_client.delete(f"/admin/slots/{slot_id}")
    assert del_resp.status_code == 409
    assert del_resp.json()["detail"]["error"]["code"] == "slot_booked"


# --- Month view ---


@pytest.mark.anyio()
async def test_month_view_lists_slots(admin_client: AsyncClient) -> None:
    doctor_id, _ = await _setup_doctor(admin_client)
    await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T09:00:00Z"},
    )
    await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2026-12-01T10:00:00Z"},
    )
    await admin_client.post(
        "/admin/slots",
        json={"doctor_id": doctor_id, "start_at": "2027-01-05T10:00:00Z"},
    )

    resp = await admin_client.get(
        "/admin/slots", params={"doctor_id": doctor_id, "year": 2026, "month": 12}
    )
    assert resp.status_code == 200
    slots = resp.json()
    assert len(slots) == 2
    assert all(s["doctor_id"] == doctor_id for s in slots)
