from __future__ import annotations

import asyncio
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

    # Create user via signup + profile
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/signup", json={"username": "user1", "password": "userpass1"})
        await c.post("/auth/login", json={"username": "user1", "password": "userpass1"})

        # Get location for profile
        locs = (await c.get("/locations")).json()
        loc_id = locs[0]["id"]
        await c.post("/me/profile", json={"name": "Test User", "location_id": loc_id})

        # Create a chat session directly in DB
        with db_engine.connect() as conn:
            profile_id = conn.execute(
                text("SELECT id FROM profile WHERE account_id = (SELECT id FROM account WHERE username = 'user1')")
            ).scalar_one()
            conn.execute(
                text("INSERT INTO chat_session (profile_id) VALUES (:p)"), {"p": profile_id}
            )
            conn.commit()

        yield c  # type: ignore[misc]


@pytest.fixture()
def setup_slot(db_engine: Engine) -> int:
    with db_engine.connect() as conn:
        loc_id: int = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        clinic_id: int = conn.execute(
            text("INSERT INTO clinic (name, location_id) VALUES ('TestClinic', :l) RETURNING id"),
            {"l": loc_id},
        ).scalar_one()
        spec_id: int = conn.execute(
            text("INSERT INTO specialty (name) VALUES ('TestSpec') RETURNING id")
        ).scalar_one()
        cs_id: int = conn.execute(
            text("INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s) RETURNING id"),
            {"c": clinic_id, "s": spec_id},
        ).scalar_one()
        doctor_id: int = conn.execute(
            text("INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr Test', :cs) RETURNING id"),
            {"cs": cs_id},
        ).scalar_one()
        slot_id: int = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at) VALUES (:d, '2026-12-15 10:00:00+00') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        conn.commit()
    return slot_id


def _get_chat_session_id(db_engine: Engine) -> int:
    with db_engine.connect() as conn:
        return conn.execute(text("SELECT id FROM chat_session LIMIT 1")).scalar_one()  # type: ignore[no-any-return]


@pytest.mark.anyio()
async def test_D1_concurrent_booking(
    user_client: AsyncClient, setup_slot: int, db_engine: Engine, app: object
) -> None:
    session_id = _get_chat_session_id(db_engine)

    async def try_book() -> int:
        resp = await user_client.post(
            "/me/visits",
            json={"session_id": session_id, "slot_id": setup_slot},
        )
        return resp.status_code

    results = await asyncio.gather(try_book(), try_book())
    assert sorted(results) == [201, 409]


@pytest.mark.anyio()
async def test_D6_booking_writes_4_messages(
    user_client: AsyncClient, setup_slot: int, db_engine: Engine
) -> None:
    session_id = _get_chat_session_id(db_engine)
    resp = await user_client.post(
        "/me/visits",
        json={"session_id": session_id, "slot_id": setup_slot},
    )
    assert resp.status_code == 201
    data = resp.json()
    messages = data["messages"]
    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Book Dr Test on Tue 15 Dec, 10:00 UTC."
    assert messages[1]["role"] == "assistant"
    assert messages[1]["tool_calls"] is not None
    assert messages[1]["tool_calls"][0]["function"]["name"] == "book_visit"
    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_name"] == "book_visit"
    assert messages[3]["role"] == "assistant"
    assert "booked" in messages[3]["content"].lower()


@pytest.mark.anyio()
async def test_D1_past_slot_rejected(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    with db_engine.connect() as conn:
        loc_id = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        clinic_id = conn.execute(
            text("INSERT INTO clinic (name, location_id) VALUES ('C2', :l) RETURNING id"),
            {"l": loc_id},
        ).scalar_one()
        spec_id = conn.execute(
            text("INSERT INTO specialty (name) VALUES ('S2') RETURNING id")
        ).scalar_one()
        cs_id = conn.execute(
            text("INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s) RETURNING id"),
            {"c": clinic_id, "s": spec_id},
        ).scalar_one()
        doctor_id = conn.execute(
            text("INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr Past', :cs) RETURNING id"),
            {"cs": cs_id},
        ).scalar_one()
        # Past slot: Dec 1 at 07:00, clock is at Dec 1 08:00
        past_slot_id = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at) VALUES (:d, '2026-12-01 07:00:00+00') RETURNING id"),
            {"d": doctor_id},
        ).scalar_one()
        conn.commit()

    session_id = _get_chat_session_id(db_engine)
    resp = await user_client.post(
        "/me/visits",
        json={"session_id": session_id, "slot_id": past_slot_id},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"]["code"] == "slot_past"


@pytest.mark.anyio()
async def test_F2_session_not_owned_rejected(
    user_client: AsyncClient, setup_slot: int, db_engine: Engine
) -> None:
    # Create another user's chat session
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
        other_session_id = conn.execute(
            text("INSERT INTO chat_session (profile_id) VALUES (:p) RETURNING id"),
            {"p": other_profile_id},
        ).scalar_one()
        conn.commit()

    resp = await user_client.post(
        "/me/visits",
        json={"session_id": other_session_id, "slot_id": setup_slot},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "not_found"
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM visit")).scalar_one() == 0
        assert conn.execute(
            text("SELECT count(*) FROM chat_message WHERE session_id = :s"), {"s": other_session_id}
        ).scalar_one() == 0
        assert conn.execute(text("SELECT status FROM slot WHERE id = :s"), {"s": setup_slot}).scalar_one() == "available"


@pytest.mark.anyio()
async def test_D1_failure_leaves_no_messages(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    # Try to book a nonexistent slot
    session_id = _get_chat_session_id(db_engine)
    msg_count_before = 0
    with db_engine.connect() as conn:
        msg_count_before = conn.execute(text("SELECT count(*) FROM chat_message")).scalar_one()

    resp = await user_client.post(
        "/me/visits",
        json={"session_id": session_id, "slot_id": 99999},
    )
    assert resp.status_code != 201

    with db_engine.connect() as conn:
        msg_count_after = conn.execute(text("SELECT count(*) FROM chat_message")).scalar_one()
    assert msg_count_after == msg_count_before


@pytest.mark.anyio()
async def test_D7_slot_taken_conflict(
    user_client: AsyncClient, setup_slot: int, db_engine: Engine
) -> None:
    session_id = _get_chat_session_id(db_engine)

    # First booking succeeds
    resp1 = await user_client.post(
        "/me/visits",
        json={"session_id": session_id, "slot_id": setup_slot},
    )
    assert resp1.status_code == 201

    msg_count_before: int
    with db_engine.connect() as conn:
        msg_count_before = conn.execute(text("SELECT count(*) FROM chat_message")).scalar_one()

    # Second booking on same slot fails with slot_taken
    resp2 = await user_client.post(
        "/me/visits",
        json={"session_id": session_id, "slot_id": setup_slot},
    )
    assert resp2.status_code == 409
    assert resp2.json()["detail"]["error"]["code"] == "slot_taken"

    # No messages written for failed booking
    with db_engine.connect() as conn:
        msg_count_after = conn.execute(text("SELECT count(*) FROM chat_message")).scalar_one()
    assert msg_count_after == msg_count_before
