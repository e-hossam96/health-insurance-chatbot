from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings
from chatbot_ai.interface import Done, HistoryRow, Token, TurnEvent, TurnRequest
from testkit.live_server import serve_in_thread
from testkit.metrics import metric_value

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot",
)
CANCEL_DEADLINE = 5.0


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


class HangingTurn:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.finished = threading.Event()

    async def __call__(self, request: TurnRequest) -> AsyncIterator[TurnEvent]:
        yield Token(text="first ", elapsed=0.0)
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        self.finished.set()
        yield Done(
            new_rows=[
                HistoryRow(role="user", content=request.message),
                HistoryRow(role="assistant", content="never"),
            ]
        )


@pytest.fixture()
def hanging_turn() -> HangingTurn:
    return HangingTurn()


@pytest.fixture()
def live_server(_clean_database: None, hanging_turn: HangingTurn) -> Iterator[str]:
    application = create_app(Settings(database_url=TEST_DB_URL))  # type: ignore[call-arg]
    application.state.clock = FixedClock()
    application.state.turn_runner = hanging_turn
    with serve_in_thread(application) as url:
        yield url


def _signed_in_cookie(base_url: str) -> str:
    with httpx.Client(base_url=base_url) as client:
        client.post("/auth/signup", json={"username": "user1", "password": "userpass1"})
        login = client.post("/auth/login", json={"username": "user1", "password": "userpass1"})
        token = login.cookies.get("session_id")
        assert token, "login did not set the session cookie"
        cookie = f"session_id={token}"
        locations = client.get("/locations", headers={"Cookie": cookie}).json()
        profile = client.post(
            "/me/profile",
            json={"name": "Test User", "location_id": locations[0]["id"]},
            headers={"Cookie": cookie},
        )
        assert profile.status_code in (200, 201)
        return cookie


def _session_count(db_engine: Engine) -> int:
    with db_engine.connect() as conn:
        count: int = conn.execute(text("SELECT count(*) FROM chat_session")).scalar_one()
        return count


def _wait_until(condition: Callable[[], bool], deadline_s: float) -> bool:
    give_up = time.monotonic() + deadline_s
    pause = threading.Event()
    while time.monotonic() < give_up:
        if condition():
            return True
        pause.wait(0.02)
    return condition()


def _chat_message_count(db_engine: Engine) -> int:
    with db_engine.connect() as conn:
        count: int = conn.execute(text("SELECT count(*) FROM chat_message")).scalar_one()
        return count


def test_F16_disconnect_cancels_turn_and_stores_nothing(
    live_server: str, hanging_turn: HangingTurn, db_engine: Engine
) -> None:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    cookie = _signed_in_cookie(live_server)
    cancelled_before = metric_value(httpx.get(f"{live_server}/metrics").text, "chat_turns_total", {"outcome": "cancelled"})

    events: list[str] = []
    with httpx.Client(base_url=live_server) as client, client.stream(
        "POST", "/me/chat", json={"message": "hello"}, headers={"Cookie": cookie}
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("event: "):
                events.append(line.removeprefix("event: "))
            if events and events[-1] == "token" and line.startswith("data: "):
                assert json.loads(line.removeprefix("data: ")) == {"text": "first "}
                break

    assert events == ["session", "token"]
    assert hanging_turn.started.is_set()
    assert hanging_turn.cancelled.wait(CANCEL_DEADLINE), "turn was not cancelled after the client disconnected"
    assert not hanging_turn.finished.is_set()
    assert _chat_message_count(db_engine) == 0
    assert _wait_until(lambda: _session_count(db_engine) == 0, CANCEL_DEADLINE), "the empty session was not removed"

    def cancelled_counted() -> bool:
        exposition = httpx.get(f"{live_server}/metrics").text
        return metric_value(exposition, "chat_turns_total", {"outcome": "cancelled"}) == cancelled_before + 1

    assert _wait_until(cancelled_counted, CANCEL_DEADLINE), "H3: the disconnected turn was not counted as cancelled"
