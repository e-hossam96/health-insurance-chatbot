from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings, get_settings

TEST_DB_URL = get_settings().database_url
MISSING = 987654


@dataclass(frozen=True)
class OtherMember:
    session: int
    scheduled_visit: int
    completed_visit: int
    complaint: int
    taken_slot: int
    free_slot: int


@pytest.fixture()
def app(_clean_database: None) -> FastAPI:
    return create_app(Settings(), ai_from_env=False)  # type: ignore[call-arg]


async def _member(app: FastAPI, username: str) -> AsyncClient:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="https://test")
    await client.post(
        "/auth/signup", json={"username": username, "password": "password123"}
    )
    locations = (await client.get("/locations")).json()
    await client.post(
        "/me/profile",
        json={"name": username.title(), "location_id": locations[0]["id"]},
    )
    return client


def _seed_other_member(engine: Engine) -> OtherMember:
    def one(conn: object, sql: str, **params: object) -> int:
        value: int = conn.execute(text(sql + " RETURNING id"), params).scalar_one()  # type: ignore[attr-defined]
        return value

    with engine.begin() as conn:
        profile = conn.execute(
            text(
                "SELECT p.id FROM profile p JOIN account a ON a.id = p.account_id WHERE a.username = 'omar'"
            )
        ).scalar_one()
        location = conn.execute(
            text("SELECT id FROM location WHERE name = 'TestCity'")
        ).scalar_one()
        specialty = one(conn, "INSERT INTO specialty (name) VALUES ('Cardiology')")
        clinic = one(
            conn,
            "INSERT INTO clinic (name, location_id) VALUES ('Giza Clinic', :l)",
            l=location,
        )
        clinic_specialty = one(
            conn,
            "INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s)",
            c=clinic,
            s=specialty,
        )
        doctor = one(
            conn,
            "INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr. Omar Adel', :cs)",
            cs=clinic_specialty,
        )
        slots = [
            one(
                conn,
                "INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, :t, :s)",
                d=doctor,
                t=start,
                s=status,
            )
            for start, status in (
                ("2026-12-15 10:00+00", "booked"),
                ("2026-11-02 10:00+00", "booked"),
                ("2026-12-16 10:00+00", "available"),
            )
        ]
        session = one(
            conn, "INSERT INTO chat_session (profile_id) VALUES (:p)", p=profile
        )
        scheduled = one(
            conn,
            "INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, 'scheduled')",
            p=profile,
            s=slots[0],
        )
        completed = one(
            conn,
            "INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, 'completed')",
            p=profile,
            s=slots[1],
        )
        complaint = one(
            conn,
            "INSERT INTO complaint (visit_id, description) VALUES (:v, 'Late doctor')",
            v=completed,
        )
    return OtherMember(session, scheduled, completed, complaint, slots[0], slots[2])


@pytest.fixture()
async def mona_and_omar(
    app: FastAPI, db_engine: Engine
) -> AsyncIterator[tuple[AsyncClient, OtherMember, int]]:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    mona = await _member(app, "mona")
    omar = await _member(app, "omar")
    await omar.aclose()
    other = _seed_other_member(db_engine)
    with db_engine.begin() as conn:
        mona_session: int = conn.execute(
            text(
                "INSERT INTO chat_session (profile_id) SELECT p.id FROM profile p JOIN account a ON a.id = p.account_id WHERE a.username = 'mona' RETURNING id"
            )
        ).scalar_one()
    yield mona, other, mona_session
    await mona.aclose()


def _assert_hidden(response: Response, missing: Response, *ids: int) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["error"]["code"] == "not_found"
    assert response.json() == missing.json(), (
        "another member's resource must look exactly like a missing one"
    )
    for value in ids:
        assert str(value) not in response.text, f"the error echoes {value}"


@pytest.mark.anyio()
async def test_B8_another_members_resources_look_exactly_like_missing_ones(
    mona_and_omar: tuple[AsyncClient, OtherMember, int],
) -> None:
    mona, other, mine = mona_and_omar
    cases: list[
        tuple[str, str, dict[str, object] | None, int, str, dict[str, object] | None]
    ] = [
        (
            "GET",
            f"/me/sessions/{other.session}/messages",
            None,
            other.session,
            f"/me/sessions/{MISSING}/messages",
            None,
        ),
        (
            "POST",
            "/me/chat",
            {"session_id": other.session, "message": "hi"},
            other.session,
            "/me/chat",
            {"session_id": MISSING, "message": "hi"},
        ),
        (
            "POST",
            f"/me/visits/{other.scheduled_visit}/cancel",
            {"session_id": None},
            other.scheduled_visit,
            f"/me/visits/{MISSING}/cancel",
            {"session_id": None},
        ),
        (
            "POST",
            "/me/visits",
            {"session_id": other.session, "slot_id": other.free_slot},
            other.session,
            "/me/visits",
            {"session_id": MISSING, "slot_id": other.free_slot},
        ),
        (
            "POST",
            "/me/complaints",
            {
                "session_id": mine,
                "visit_id": other.completed_visit,
                "description": "Rude staff",
            },
            other.completed_visit,
            "/me/complaints",
            {"session_id": mine, "visit_id": MISSING, "description": "Rude staff"},
        ),
        (
            "POST",
            "/me/complaints",
            {
                "session_id": other.session,
                "visit_id": other.completed_visit,
                "description": "Rude staff",
            },
            other.session,
            "/me/complaints",
            {
                "session_id": MISSING,
                "visit_id": other.completed_visit,
                "description": "Rude staff",
            },
        ),
    ]
    for method, path, body, hidden_id, missing_path, missing_body in cases:
        response = await mona.request(method, path, json=body)
        missing = await mona.request(method, missing_path, json=missing_body)
        _assert_hidden(response, missing, hidden_id, MISSING)


@pytest.mark.anyio()
async def test_B8_conflicts_and_validation_errors_do_not_echo_ids_or_input(
    mona_and_omar: tuple[AsyncClient, OtherMember, int],
) -> None:
    mona, other, mine = mona_and_omar
    taken = await mona.post(
        "/me/visits", json={"session_id": mine, "slot_id": other.taken_slot}
    )
    assert taken.status_code == 409
    assert str(other.taken_slot) not in taken.text and str(mine) not in taken.text

    invalid = await mona.post(
        "/me/visits", json={"session_id": "secret-987654", "slot_id": 1}
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["error"]["code"] == "validation_error"
    assert (
        "secret-987654" not in invalid.text and "input" not in invalid.json()["detail"]
    )


@pytest.mark.anyio()
async def test_B8_admin_not_found_errors_do_not_echo_ids(app: FastAPI) -> None:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as admin:
        await admin.post(
            "/auth/login", json={"username": "admin1", "password": "adminpass1"}
        )
        for method, path, body in (
            ("DELETE", f"/admin/clinics/{MISSING}", None),
            ("PUT", f"/admin/clinics/{MISSING}/specialties", []),
            ("POST", f"/admin/complaints/{MISSING}/close", None),
            (
                "POST",
                f"/admin/complaints/{MISSING}/reply",
                {"body": "Sorry about that."},
            ),
            ("DELETE", f"/admin/doctors/{MISSING}", None),
            ("DELETE", f"/admin/kb-documents/{MISSING}", None),
            ("POST", f"/admin/kb-documents/{MISSING}/reindex", None),
            ("DELETE", f"/admin/locations/{MISSING}", None),
            ("DELETE", f"/admin/slots/{MISSING}", None),
            ("DELETE", f"/admin/specialties/{MISSING}", None),
            ("POST", f"/admin/visits/{MISSING}/complete", None),
        ):
            response = await admin.request(method, path, json=body)
            assert response.status_code == 404, (
                f"{method} {path}: {response.status_code} {response.text}"
            )
            assert response.json()["detail"]["error"]["code"] == "not_found"
            assert str(MISSING) not in response.text, f"{method} {path} echoes the id"
