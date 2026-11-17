from __future__ import annotations

import os
from datetime import UTC, datetime

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


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture()
def app(_clean_database: None) -> object:
    settings = Settings(database_url=TEST_DB_URL)  # type: ignore[call-arg]
    application = create_app(settings)
    application.state.clock = FakeClock(datetime(2026, 12, 1, 8, 0, tzinfo=UTC))  # type: ignore[union-attr]
    return application


@pytest.fixture()
async def user_client(app: object, db_engine: Engine) -> AsyncClient:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")

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
async def admin_client(app: object) -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
        yield c  # type: ignore[misc]


def _setup_completed_visit(db_engine: Engine) -> int:
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
        slot_id = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-15 10:00:00+00', 'booked') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        profile_id = conn.execute(
            text("SELECT id FROM profile WHERE account_id = (SELECT id FROM account WHERE username = 'user1')")
        ).scalar_one()
        visit_id = conn.execute(
            text("INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, 'completed') RETURNING id"),
            {"p": profile_id, "s": slot_id},
        ).scalar_one()
        conn.commit()
    return visit_id


def _get_chat_session_id(db_engine: Engine) -> int:
    with db_engine.connect() as conn:
        return conn.execute(text("SELECT id FROM chat_session LIMIT 1")).scalar_one()  # type: ignore[no-any-return]


# --- E1: only on completed visit ---


@pytest.mark.anyio()
async def test_E1_file_complaint_on_completed_visit(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_completed_visit(db_engine)
    session_id = _get_chat_session_id(db_engine)
    resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Bad service"},
    )
    assert resp.status_code == 201
    assert resp.json()["complaint"]["status"] == "open"


@pytest.mark.anyio()
async def test_E1_file_complaint_on_scheduled_visit_rejected(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    with db_engine.connect() as conn:
        loc_id = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        clinic_id = conn.execute(
            text("INSERT INTO clinic (name, location_id) VALUES ('C2', :l) RETURNING id"), {"l": loc_id}
        ).scalar_one()
        spec_id = conn.execute(text("INSERT INTO specialty (name) VALUES ('S2') RETURNING id")).scalar_one()
        cs_id = conn.execute(
            text("INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s) RETURNING id"),
            {"c": clinic_id, "s": spec_id},
        ).scalar_one()
        doctor_id = conn.execute(
            text("INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr2', :cs) RETURNING id"),
            {"cs": cs_id},
        ).scalar_one()
        slot_id = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-15 11:00:00+00', 'booked') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        profile_id = conn.execute(
            text("SELECT id FROM profile WHERE account_id = (SELECT id FROM account WHERE username = 'user1')")
        ).scalar_one()
        visit_id = conn.execute(
            text("INSERT INTO visit (profile_id, slot_id) VALUES (:p, :s) RETURNING id"),
            {"p": profile_id, "s": slot_id},
        ).scalar_one()
        conn.commit()

    session_id = _get_chat_session_id(db_engine)
    resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Bad"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "visit_not_completed"


# --- E2: one per visit ---


@pytest.mark.anyio()
async def test_E2_one_complaint_per_visit(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_completed_visit(db_engine)
    session_id = _get_chat_session_id(db_engine)
    resp1 = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Bad service"},
    )
    assert resp1.status_code == 201

    resp2 = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Also bad"},
    )
    assert resp2.status_code == 409
    assert resp2.json()["detail"]["error"]["code"] == "complaint_exists"


# --- E6: static messages ---


@pytest.mark.anyio()
async def test_E6_complaint_writes_static_messages(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_completed_visit(db_engine)
    session_id = _get_chat_session_id(db_engine)
    resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Bad service"},
    )
    assert resp.status_code == 201
    messages = resp.json()["messages"]
    assert len(messages) == 4
    assert messages[0]["content"] == "File a complaint about my visit with Dr on Tue 15 Dec, 10:00 UTC."
    assert messages[1]["tool_calls"][0]["function"]["name"] == "file_complaint"
    assert messages[2]["tool_name"] == "file_complaint"


# --- E3: only admins reply ---


@pytest.mark.anyio()
async def test_E3_admin_replies_to_complaint(
    user_client: AsyncClient, admin_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_completed_visit(db_engine)
    session_id = _get_chat_session_id(db_engine)
    file_resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Bad service"},
    )
    complaint_id = file_resp.json()["complaint"]["id"]

    reply_resp = await admin_client.post(
        f"/admin/complaints/{complaint_id}/reply",
        json={"body": "We apologize."},
    )
    assert reply_resp.status_code == 201
    assert reply_resp.json()["body"] == "We apologize."


# --- E4: reply doesn't change status ---


@pytest.mark.anyio()
async def test_E4_reply_does_not_change_status(
    user_client: AsyncClient, admin_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_completed_visit(db_engine)
    session_id = _get_chat_session_id(db_engine)
    file_resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Bad"},
    )
    complaint_id = file_resp.json()["complaint"]["id"]

    await admin_client.post(
        f"/admin/complaints/{complaint_id}/reply",
        json={"body": "Noted."},
    )

    with db_engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM complaint WHERE id = :c"), {"c": complaint_id}
        ).scalar_one()
    assert status == "open"


# --- E5: replies on closed complaint rejected ---


@pytest.mark.anyio()
async def test_E5_reply_on_closed_complaint_rejected(
    user_client: AsyncClient, admin_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_completed_visit(db_engine)
    session_id = _get_chat_session_id(db_engine)
    file_resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Bad"},
    )
    complaint_id = file_resp.json()["complaint"]["id"]

    # Close it
    close_resp = await admin_client.post(f"/admin/complaints/{complaint_id}/close")
    assert close_resp.status_code == 200

    # Try to reply
    reply_resp = await admin_client.post(
        f"/admin/complaints/{complaint_id}/reply",
        json={"body": "Too late."},
    )
    assert reply_resp.status_code == 409
    assert reply_resp.json()["detail"]["error"]["code"] == "complaint_closed"


# --- B7: admin_account_id references admin role ---


@pytest.mark.anyio()
async def test_B7_complaint_reply_admin_account_id(
    user_client: AsyncClient, admin_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_completed_visit(db_engine)
    session_id = _get_chat_session_id(db_engine)
    file_resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Bad"},
    )
    complaint_id = file_resp.json()["complaint"]["id"]

    reply_resp = await admin_client.post(
        f"/admin/complaints/{complaint_id}/reply",
        json={"body": "Reply."},
    )
    assert reply_resp.status_code == 201

    with db_engine.connect() as conn:
        admin_id = reply_resp.json()["admin_account_id"]
        role = conn.execute(
            text("SELECT role FROM account WHERE id = :a"), {"a": admin_id}
        ).scalar_one()
    assert role == "admin"


# --- E1: complaint on another user's visit rejected ---


@pytest.mark.anyio()
async def test_E1_complaint_on_other_users_visit_rejected(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    # Create another user's completed visit
    with db_engine.connect() as conn:
        from argon2 import PasswordHasher

        ph = PasswordHasher()
        acct_id = conn.execute(
            text("INSERT INTO account (username, password_hash, role) VALUES ('other', :h, 'user') RETURNING id"),
            {"h": ph.hash("otherpass")},
        ).scalar_one()
        loc_id = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        other_profile_id = conn.execute(
            text("INSERT INTO profile (account_id, name, location_id) VALUES (:a, 'Other', :l) RETURNING id"),
            {"a": acct_id, "l": loc_id},
        ).scalar_one()
        clinic_id = conn.execute(
            text("INSERT INTO clinic (name, location_id) VALUES ('OC', :l) RETURNING id"), {"l": loc_id}
        ).scalar_one()
        spec_id = conn.execute(text("INSERT INTO specialty (name) VALUES ('OS') RETURNING id")).scalar_one()
        cs_id = conn.execute(
            text("INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s) RETURNING id"),
            {"c": clinic_id, "s": spec_id},
        ).scalar_one()
        doctor_id = conn.execute(
            text("INSERT INTO doctor (name, clinic_specialty_id) VALUES ('DrO', :cs) RETURNING id"),
            {"cs": cs_id},
        ).scalar_one()
        slot_id = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-15 12:00:00+00', 'booked') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        other_visit_id = conn.execute(
            text("INSERT INTO visit (profile_id, slot_id, status) VALUES (:p, :s, 'completed') RETURNING id"),
            {"p": other_profile_id, "s": slot_id},
        ).scalar_one()
        conn.commit()

    session_id = _get_chat_session_id(db_engine)
    resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": other_visit_id, "description": "Not mine"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "not_found"


# --- E3: user cannot reply to complaint ---


@pytest.mark.anyio()
async def test_E3_user_reply_rejected(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_completed_visit(db_engine)
    session_id = _get_chat_session_id(db_engine)
    file_resp = await user_client.post(
        "/me/complaints",
        json={"session_id": session_id, "visit_id": visit_id, "description": "Bad"},
    )
    complaint_id = file_resp.json()["complaint"]["id"]

    # user_client is in user mode, should be rejected
    resp = await user_client.post(
        f"/admin/complaints/{complaint_id}/reply",
        json={"body": "I am not admin."},
    )
    assert resp.status_code == 403


@pytest.mark.anyio()
async def test_F2_complaint_with_other_users_session_rejected(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id = _setup_completed_visit(db_engine)
    with db_engine.connect() as conn:
        acct_id = conn.execute(
            text("INSERT INTO account (username, password_hash, role) VALUES ('other', 'x', 'user') RETURNING id")
        ).scalar_one()
        loc_id = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        profile_id = conn.execute(
            text("INSERT INTO profile (account_id, name, location_id) VALUES (:a, 'Other', :l) RETURNING id"),
            {"a": acct_id, "l": loc_id},
        ).scalar_one()
        other_session_id = conn.execute(
            text("INSERT INTO chat_session (profile_id) VALUES (:p) RETURNING id"), {"p": profile_id}
        ).scalar_one()
        conn.commit()

    resp = await user_client.post(
        "/me/complaints",
        json={"session_id": other_session_id, "visit_id": visit_id, "description": "Bad service"},
    )

    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "not_found"
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM complaint")).scalar_one() == 0
        assert conn.execute(
            text("SELECT count(*) FROM chat_message WHERE session_id = :s"), {"s": other_session_id}
        ).scalar_one() == 0
