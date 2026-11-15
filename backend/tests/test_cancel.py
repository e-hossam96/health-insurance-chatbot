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
def app(_migrate_fresh: None) -> object:
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


def _setup_booked_visit(db_engine: Engine) -> tuple[int, int]:
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
            text("INSERT INTO visit (profile_id, slot_id) VALUES (:p, :s) RETURNING id"),
            {"p": profile_id, "s": slot_id},
        ).scalar_one()
        conn.commit()
    return visit_id, slot_id


def _get_chat_session_id(db_engine: Engine) -> int:
    with db_engine.connect() as conn:
        return conn.execute(text("SELECT id FROM chat_session LIMIT 1")).scalar_one()  # type: ignore[no-any-return]


@pytest.mark.anyio()
async def test_D2_cancel_own_scheduled_visit(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id, slot_id = _setup_booked_visit(db_engine)
    resp = await user_client.post(f"/me/visits/{visit_id}/cancel", json={})
    assert resp.status_code == 200
    assert resp.json()["visit"]["status"] == "cancelled"

    # Slot should be available again
    with db_engine.connect() as conn:
        status = conn.execute(
            text("SELECT status FROM slot WHERE id = :s"), {"s": slot_id}
        ).scalar_one()
    assert status == "available"


@pytest.mark.anyio()
async def test_D8_cancel_with_session_writes_messages(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id, _ = _setup_booked_visit(db_engine)
    session_id = _get_chat_session_id(db_engine)
    resp = await user_client.post(
        f"/me/visits/{visit_id}/cancel",
        json={"session_id": session_id},
    )
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[1]["tool_calls"][0]["function"]["name"] == "cancel_visit"
    assert messages[2]["role"] == "tool"
    assert messages[3]["role"] == "assistant"


@pytest.mark.anyio()
async def test_D8_cancel_without_session_no_messages(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id, _ = _setup_booked_visit(db_engine)
    resp = await user_client.post(f"/me/visits/{visit_id}/cancel", json={})
    assert resp.status_code == 200
    assert resp.json()["messages"] is None


@pytest.mark.anyio()
async def test_D2_cancel_other_users_visit_404(
    user_client: AsyncClient, db_engine: Engine
) -> None:
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

        # Create a visit for the other user
        clinic_id = conn.execute(
            text("INSERT INTO clinic (name, location_id) VALUES ('OC', :l) RETURNING id"), {"l": loc_id}
        ).scalar_one()
        spec_id = conn.execute(text("INSERT INTO specialty (name) VALUES ('OS') RETURNING id")).scalar_one()
        cs_id = conn.execute(
            text("INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s) RETURNING id"),
            {"c": clinic_id, "s": spec_id},
        ).scalar_one()
        doctor_id = conn.execute(
            text("INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr O', :cs) RETURNING id"),
            {"cs": cs_id},
        ).scalar_one()
        slot_id = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-15 11:00:00+00', 'booked') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        other_visit_id = conn.execute(
            text("INSERT INTO visit (profile_id, slot_id) VALUES (:p, :s) RETURNING id"),
            {"p": other_profile, "s": slot_id},
        ).scalar_one()
        conn.commit()

    resp = await user_client.post(f"/me/visits/{other_visit_id}/cancel", json={})
    assert resp.status_code == 404


@pytest.mark.anyio()
async def test_D2_cancel_completed_visit_rejected(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id, _ = _setup_booked_visit(db_engine)
    # Mark as completed
    with db_engine.connect() as conn:
        conn.execute(text("UPDATE visit SET status = 'completed' WHERE id = :v"), {"v": visit_id})
        conn.commit()

    resp = await user_client.post(f"/me/visits/{visit_id}/cancel", json={})
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "visit_not_cancellable"
