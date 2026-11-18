from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings, get_settings

TEST_DB_URL = get_settings().database_url


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture()
def app(_clean_database: None) -> object:
    settings = Settings()  # type: ignore[call-arg]
    application = create_app(settings)
    application.state.clock = FakeClock(datetime(2026, 12, 1, 8, 0, tzinfo=UTC))  # type: ignore[union-attr]
    return application


@pytest.fixture()
def _setup_accounts(app: object) -> None:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")


@pytest.fixture()
async def user_client(app: object, _setup_accounts: None, db_engine: Engine) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/signup", json={"username": "user1", "password": "userpass1"})
        await c.post("/auth/login", json={"username": "user1", "password": "userpass1"})
        locs = (await c.get("/locations")).json()
        await c.post("/me/profile", json={"name": "Test User", "location_id": locs[0]["id"]})

        with db_engine.connect() as conn:
            profile_id = conn.execute(
                text("SELECT id FROM profile WHERE account_id = (SELECT id FROM account WHERE username = 'user1')")
            ).scalar_one()
            conn.execute(text("INSERT INTO chat_session (profile_id) VALUES (:p)"), {"p": profile_id})
            conn.commit()

        yield c  # type: ignore[misc]


@pytest.fixture()
async def admin_client(app: object, _setup_accounts: None) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
        yield c  # type: ignore[misc]


def _setup_visit_data(db_engine: Engine) -> dict[str, int]:
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

        profile_id = conn.execute(
            text("SELECT id FROM profile WHERE account_id = (SELECT id FROM account WHERE username = 'user1')")
        ).scalar_one()

        slot1 = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-10 10:00:00+00', 'booked') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        v1 = conn.execute(
            text("INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, 'completed') RETURNING id"),
            {"p": profile_id, "s": slot1},
        ).scalar_one()

        slot2 = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-11 10:00:00+00', 'booked') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        v2 = conn.execute(
            text("INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, 'completed') RETURNING id"),
            {"p": profile_id, "s": slot2},
        ).scalar_one()

        slot3 = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-15 10:00:00+00', 'booked') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        v3 = conn.execute(
            text("INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, 'scheduled') RETURNING id"),
            {"p": profile_id, "s": slot3},
        ).scalar_one()

        conn.commit()
    return {"v1": v1, "v2": v2, "v3": v3, "doctor_id": doctor_id}


def _get_chat_session_id(db_engine: Engine) -> int:
    with db_engine.connect() as conn:
        return conn.execute(text("SELECT id FROM chat_session LIMIT 1")).scalar_one()  # type: ignore[no-any-return]


@pytest.mark.anyio()
async def test_D4_my_visits_with_joins(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    _setup_visit_data(db_engine)
    resp = await user_client.get("/me/visits")
    assert resp.status_code == 200
    visits = resp.json()
    assert len(visits) == 3
    # D4: derived fields present
    assert "doctor_name" in visits[0]
    assert "specialty" in visits[0]
    assert "clinic" in visits[0]
    assert "location" in visits[0]
    # Ordered by start_at desc
    assert visits[0]["status"] == "scheduled"


@pytest.mark.anyio()
async def test_D4_my_visits_no_leakage(
    user_client: AsyncClient, db_engine: Engine, app: object
) -> None:
    _setup_visit_data(db_engine)

    # Create another user and visit
    with db_engine.connect() as conn:
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        other_acct = conn.execute(
            text("INSERT INTO account (username, password_hash, role) VALUES ('other', :h, 'user') RETURNING id"),
            {"h": ph.hash("otherpass")},
        ).scalar_one()
        loc_id = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        other_profile = conn.execute(
            text("INSERT INTO profile (account_id, name, location_id) VALUES (:a, 'Other', :l) RETURNING id"),
            {"a": other_acct, "l": loc_id},
        ).scalar_one()
        doctor_id = conn.execute(text("SELECT id FROM doctor LIMIT 1")).scalar_one()
        slot_id = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-20 10:00:00+00', 'booked') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO visit (profile_id, slot_id) VALUES (:p, :s)"),
            {"p": other_profile, "s": slot_id},
        )
        conn.commit()

    resp = await user_client.get("/me/visits")
    # Should only see user1's 3 visits, not the other user's
    assert len(resp.json()) == 3


@pytest.mark.anyio()
async def test_D4_my_complaints_with_replies(
    user_client: AsyncClient, admin_client: AsyncClient, db_engine: Engine
) -> None:
    ids = _setup_visit_data(db_engine)
    session_id = _get_chat_session_id(db_engine)

    # File a complaint on completed visit
    file_resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": ids["v1"], "description": "Bad"},
    )
    complaint_id = file_resp.json()["complaint"]["id"]

    # Admin replies
    await admin_client.post(
        f"/admin/complaints/{complaint_id}/reply",
        json={"body": "Sorry."},
    )

    resp = await user_client.get("/me/complaints")
    assert resp.status_code == 200
    complaints = resp.json()
    assert len(complaints) == 1
    assert len(complaints[0]["replies"]) == 1
    assert complaints[0]["replies"][0]["body"] == "Sorry."


@pytest.mark.anyio()
async def test_D4_admin_visits_pagination(
    admin_client: AsyncClient, db_engine: Engine, user_client: AsyncClient
) -> None:
    _setup_visit_data(db_engine)

    resp = await admin_client.get("/admin/visits", params={"limit": 2, "offset": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    resp2 = await admin_client.get("/admin/visits", params={"limit": 2, "offset": 2})
    assert len(resp2.json()["items"]) == 1


@pytest.mark.anyio()
async def test_D4_admin_visits_filter(
    admin_client: AsyncClient, db_engine: Engine, user_client: AsyncClient
) -> None:
    _setup_visit_data(db_engine)

    resp = await admin_client.get("/admin/visits", params={"status": "completed"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(v["status"] == "completed" for v in data["items"])


@pytest.mark.anyio()
async def test_D4_admin_complaints_list(
    user_client: AsyncClient, admin_client: AsyncClient, db_engine: Engine
) -> None:
    ids = _setup_visit_data(db_engine)
    session_id = _get_chat_session_id(db_engine)

    await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": ids["v1"], "description": "Bad1"},
    )
    await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": ids["v2"], "description": "Bad2"},
    )

    resp = await admin_client.get("/admin/complaints")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.anyio()
async def test_D4_admin_visits_carry_patient_and_catalog_names(
    admin_client: AsyncClient, db_engine: Engine, user_client: AsyncClient
) -> None:
    ids = _setup_visit_data(db_engine)

    data = (await admin_client.get("/admin/visits")).json()

    assert [v["id"] for v in data["items"]] == [ids["v3"], ids["v2"], ids["v1"]]
    first = data["items"][0]
    assert first["patient_name"] == "Test User"
    assert first["location"] == "TestCity"
    assert (first["clinic"], first["specialty"], first["doctor_name"]) == ("C", "S", "Dr")
    assert first["start_at"] == "2026-12-15T10:00:00+00:00"


@pytest.mark.anyio()
async def test_D4_admin_visits_patient_search_and_visit_filter(
    admin_client: AsyncClient, db_engine: Engine, user_client: AsyncClient
) -> None:
    ids = _setup_visit_data(db_engine)

    found = (await admin_client.get("/admin/visits", params={"patient": "test us"})).json()
    wildcard = (await admin_client.get("/admin/visits", params={"patient": "%"})).json()
    one = (await admin_client.get("/admin/visits", params={"visit_id": ids["v2"]})).json()

    assert found["total"] == 3
    assert wildcard["total"] == 0
    assert [v["id"] for v in one["items"]] == [ids["v2"]]


@pytest.mark.anyio()
async def test_D4_admin_lists_default_to_50_rows(
    admin_client: AsyncClient, db_engine: Engine, user_client: AsyncClient
) -> None:
    _setup_visit_data(db_engine)
    with db_engine.connect() as conn:
        doctor_id = conn.execute(text("SELECT id FROM doctor LIMIT 1")).scalar_one()
        profile_id = conn.execute(text("SELECT id FROM profile WHERE name = 'Test User'")).scalar_one()
        for day in range(1, 26):
            for hour in (9, 10):
                slot_id = conn.execute(
                    text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, :t, 'booked') RETURNING id"),
                    {"d": doctor_id, "t": datetime(2027, 1, day, hour, tzinfo=UTC)},
                ).scalar_one()
                conn.execute(
                    text("INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, 'scheduled')"),
                    {"p": profile_id, "s": slot_id},
                )
        conn.commit()

    data = (await admin_client.get("/admin/visits")).json()

    assert data["total"] == 53
    assert len(data["items"]) == 50


@pytest.mark.anyio()
async def test_E4_admin_complaint_list_and_detail_show_patient_visit_and_replies(
    user_client: AsyncClient, admin_client: AsyncClient, db_engine: Engine
) -> None:
    ids = _setup_visit_data(db_engine)
    session_id = _get_chat_session_id(db_engine)
    filed = await user_client.post(
        "/me/complaints", json={"session_id": session_id, "visit_id": ids["v1"], "description": "Long wait"}
    )
    complaint_id = filed.json()["complaint"]["id"]
    await admin_client.post(f"/admin/complaints/{complaint_id}/reply", json={"body": "We are sorry."})

    item = (await admin_client.get("/admin/complaints")).json()["items"][0]
    detail = (await admin_client.get(f"/admin/complaints/{complaint_id}")).json()

    assert (item["patient_name"], item["reply_count"], item["status"]) == ("Test User", 1, "open")
    assert item["created_at"]
    assert detail["patient_name"] == "Test User"
    assert detail["description"] == "Long wait"
    assert detail["visit"] == {
        "id": ids["v1"],
        "start_at": "2026-12-10T10:00:00+00:00",
        "doctor_name": "Dr",
        "specialty": "S",
        "clinic": "C",
        "location": "TestCity",
    }
    assert [(r["body"], r["admin_username"]) for r in detail["replies"]] == [("We are sorry.", "admin1")]
    assert detail["replies"][0]["created_at"]


@pytest.mark.anyio()
async def test_E4_reply_with_close_flag_closes_in_the_same_request(
    user_client: AsyncClient, admin_client: AsyncClient, db_engine: Engine
) -> None:
    ids = _setup_visit_data(db_engine)
    session_id = _get_chat_session_id(db_engine)
    open_id = (
        await user_client.post("/me/complaints", json={"session_id": session_id, "visit_id": ids["v1"], "description": "A"})
    ).json()["complaint"]["id"]
    closing_id = (
        await user_client.post("/me/complaints", json={"session_id": session_id, "visit_id": ids["v2"], "description": "B"})
    ).json()["complaint"]["id"]

    kept = await admin_client.post(f"/admin/complaints/{open_id}/reply", json={"body": "Noted."})
    closed = await admin_client.post(f"/admin/complaints/{closing_id}/reply", json={"body": "Done.", "close": True})
    after_close = await admin_client.post(f"/admin/complaints/{closing_id}/reply", json={"body": "Again."})

    assert kept.json()["complaint_status"] == "open"
    assert closed.status_code == 201
    assert closed.json()["complaint_status"] == "closed"
    assert (await admin_client.get(f"/admin/complaints/{closing_id}")).json()["status"] == "closed"
    assert after_close.status_code == 409
    assert after_close.json()["detail"]["error"]["code"] == "complaint_closed"


@pytest.mark.anyio()
async def test_admin_complaint_detail_of_missing_id_is_404(admin_client: AsyncClient) -> None:
    resp = await admin_client.get("/admin/complaints/999999")

    assert resp.status_code == 404
    assert "999999" not in resp.text


@pytest.mark.anyio()
async def test_F14_drawer_complaints_carry_dates_visit_and_reply_dates(
    user_client: AsyncClient, admin_client: AsyncClient, db_engine: Engine
) -> None:
    ids = _setup_visit_data(db_engine)
    session_id = _get_chat_session_id(db_engine)
    filed = await user_client.post(
        "/me/complaints", json={"session_id": session_id, "visit_id": ids["v1"], "description": "Bad"}
    )
    await admin_client.post(f"/admin/complaints/{filed.json()['complaint']['id']}/reply", json={"body": "Sorry."})

    complaint = (await user_client.get("/me/complaints")).json()[0]

    assert complaint["visit_start_at"] == "2026-12-10T10:00:00+00:00"
    assert complaint["doctor_name"] == "Dr"
    assert complaint["created_at"]
    assert set(complaint["replies"][0]) == {"id", "body", "created_at"}
