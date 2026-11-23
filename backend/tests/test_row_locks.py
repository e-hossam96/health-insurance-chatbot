from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection, text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings, get_settings

TEST_DB_URL = get_settings().database_url
LOCK_WAIT_DEADLINE_S = 10.0
USER_PROFILE = "SELECT p.id FROM profile p JOIN account a ON a.id = p.account_id WHERE a.username = 'user1'"


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


@pytest.fixture()
def app(_clean_database: None) -> object:
    application = create_app(Settings())  # type: ignore[call-arg]
    application.state.clock = FakeClock(datetime(2026, 12, 1, 8, 0, tzinfo=UTC))  # type: ignore[union-attr]
    return application


@pytest.fixture()
async def user_client(app: object, db_engine: Engine) -> AsyncIterator[AsyncClient]:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:  # type: ignore[arg-type]
        await client.post("/auth/signup", json={"username": "user1", "password": "userpass1"})
        await client.post("/auth/login", json={"username": "user1", "password": "userpass1"})
        locations = (await client.get("/locations")).json()
        await client.post("/me/profile", json={"name": "Test User", "location_id": locations[0]["id"]})
        with db_engine.connect() as conn:
            conn.execute(text(f"INSERT INTO chat_session (profile_id) {USER_PROFILE}"))
            conn.commit()
        yield client


@pytest.fixture()
async def admin_client(app: object, user_client: AsyncClient) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:  # type: ignore[arg-type]
        await client.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
        yield client


def _visit(db_engine: Engine, status: str) -> tuple[int, int]:
    with db_engine.connect() as conn:
        location_id = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        clinic_id = conn.execute(text("INSERT INTO clinic (name, location_id) VALUES ('C', :l) RETURNING id"), {"l": location_id}).scalar_one()
        specialty_id = conn.execute(text("INSERT INTO specialty (name) VALUES ('S') RETURNING id")).scalar_one()
        pair_id = conn.execute(
            text("INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s) RETURNING id"), {"c": clinic_id, "s": specialty_id}
        ).scalar_one()
        doctor_id = conn.execute(text("INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr', :p) RETURNING id"), {"p": pair_id}).scalar_one()
        slot_id = conn.execute(
            text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-15 10:00:00+00', 'booked') RETURNING id"), {"d": doctor_id}
        ).scalar_one()
        visit_id = conn.execute(
            text(f"INSERT INTO visit (profile_id, slot_id, status) VALUES (({USER_PROFILE}), :s, CAST(:st AS visit_status)) RETURNING id"),
            {"s": slot_id, "st": status},
        ).scalar_one()
        conn.commit()
    return int(visit_id), int(slot_id)


def _session_id(db_engine: Engine) -> int:
    with db_engine.connect() as conn:
        return int(conn.execute(text("SELECT id FROM chat_session LIMIT 1")).scalar_one())


def _scalar(db_engine: Engine, sql: str, **params: object) -> object:
    with db_engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _lock_waiters(db_engine: Engine) -> int:
    sql = "SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND datname = current_database()"
    return int(str(_scalar(db_engine, sql)))


async def _while_row_is_locked(
    db_engine: Engine, hold: Callable[[Connection], None], request: Callable[[], Awaitable[httpx.Response]]
) -> httpx.Response:
    # The other transaction holds the row lock until the request is seen waiting on it, then commits.
    with db_engine.connect() as other:
        hold(other)
        pending = asyncio.ensure_future(request())
        deadline = time.monotonic() + LOCK_WAIT_DEADLINE_S
        while await asyncio.to_thread(_lock_waiters, db_engine) == 0:
            assert not pending.done(), f"the request finished without waiting for the row lock: {pending.result().status_code}"
            assert time.monotonic() < deadline, "the request never waited for the row lock"
            await asyncio.sleep(0.01)
        other.commit()
    return await pending


@pytest.mark.anyio()
async def test_D2_D3_a_cancel_waits_for_a_concurrent_complete_and_then_refuses(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id, slot_id = _visit(db_engine, "scheduled")
    session_id = _session_id(db_engine)

    def complete(conn: Connection) -> None:
        conn.execute(text("SELECT id FROM visit WHERE id = :v FOR UPDATE"), {"v": visit_id})
        conn.execute(text("UPDATE visit SET status = 'completed' WHERE id = :v"), {"v": visit_id})

    response = await _while_row_is_locked(
        db_engine, complete, lambda: user_client.post(f"/me/visits/{visit_id}/cancel", json={"session_id": session_id})
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "visit_not_cancellable"
    assert _scalar(db_engine, "SELECT status::text FROM visit WHERE id = :v", v=visit_id) == "completed"
    assert _scalar(db_engine, "SELECT status::text FROM slot WHERE id = :s", s=slot_id) == "booked"
    assert _scalar(db_engine, "SELECT count(*) FROM chat_message") == 0


@pytest.mark.anyio()
async def test_D3_a_complete_waits_for_a_concurrent_cancel_and_then_refuses(
    admin_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id, slot_id = _visit(db_engine, "scheduled")

    def cancel(conn: Connection) -> None:
        conn.execute(text("SELECT id FROM visit WHERE id = :v FOR UPDATE"), {"v": visit_id})
        conn.execute(text("UPDATE visit SET status = 'cancelled' WHERE id = :v"), {"v": visit_id})
        conn.execute(text("UPDATE slot SET status = 'available' WHERE id = :s"), {"s": slot_id})

    response = await _while_row_is_locked(db_engine, cancel, lambda: admin_client.post(f"/admin/visits/{visit_id}/complete"))
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "invalid_transition"
    assert _scalar(db_engine, "SELECT status::text FROM visit WHERE id = :v", v=visit_id) == "cancelled"


@pytest.mark.anyio()
async def test_D2_D8_two_cancels_at_once_cancel_once_and_write_the_messages_once(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id, _ = _visit(db_engine, "scheduled")
    session_id = _session_id(db_engine)
    responses = await asyncio.gather(
        *(user_client.post(f"/me/visits/{visit_id}/cancel", json={"session_id": session_id}) for _ in range(2))
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert _scalar(db_engine, "SELECT count(*) FROM chat_message") == 4


@pytest.mark.anyio()
async def test_E2_a_complaint_filed_while_another_is_being_filed_is_a_409_not_a_500(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id, _ = _visit(db_engine, "completed")
    session_id = _session_id(db_engine)

    def file_first(conn: Connection) -> None:
        conn.execute(text("SELECT id FROM visit WHERE id = :v FOR UPDATE"), {"v": visit_id})
        conn.execute(text("INSERT INTO complaint (visit_id, description) VALUES (:v, 'first')"), {"v": visit_id})

    response = await _while_row_is_locked(
        db_engine,
        file_first,
        lambda: user_client.post("/me/complaints", json={"session_id": session_id, "visit_id": visit_id, "description": "second"}),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "complaint_exists"
    assert _scalar(db_engine, "SELECT count(*) FROM complaint") == 1


@pytest.mark.anyio()
async def test_E5_a_reply_waits_for_a_concurrent_close_and_then_refuses(
    admin_client: AsyncClient, db_engine: Engine
) -> None:
    visit_id, _ = _visit(db_engine, "completed")
    with db_engine.connect() as conn:
        complaint_id = int(conn.execute(text("INSERT INTO complaint (visit_id, description) VALUES (:v, 'late') RETURNING id"), {"v": visit_id}).scalar_one())
        conn.commit()

    def close(conn: Connection) -> None:
        conn.execute(text("SELECT id FROM complaint WHERE id = :c FOR UPDATE"), {"c": complaint_id})
        conn.execute(text("UPDATE complaint SET status = 'closed' WHERE id = :c"), {"c": complaint_id})

    response = await _while_row_is_locked(
        db_engine, close, lambda: admin_client.post(f"/admin/complaints/{complaint_id}/reply", json={"body": "We are sorry."})
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "complaint_closed"
    assert _scalar(db_engine, "SELECT count(*) FROM complaint_reply") == 0
