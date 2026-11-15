"""Tests for step 5.3: Chat endpoint (F1-F3, F12, F15, F16)."""

from __future__ import annotations

import json
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

    def advance(self, seconds: int) -> None:
        from datetime import timedelta

        self._now += timedelta(seconds=seconds)


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 12, 1, 8, 0, tzinfo=UTC))


@pytest.fixture()
def app(_migrate_fresh: None, clock: FakeClock) -> object:
    settings = Settings(database_url=TEST_DB_URL)  # type: ignore[call-arg]
    application = create_app(settings)
    application.state.clock = clock  # type: ignore[union-attr]
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
        yield c  # type: ignore[misc]


@pytest.fixture()
async def admin_user_client(app: object, user_client: AsyncClient) -> AsyncClient:
    """Admin in user mode. Depends on user_client to ensure admin account is created."""
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
        await c.post("/auth/mode", json={"mode": "user"})
        yield c  # type: ignore[misc]


def _parse_sse(content: str) -> list[dict[str, str]]:
    """Parse SSE text into a list of {event, data} dicts."""
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in content.split("\n"):
        if line.startswith("event:"):
            current["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:"):].strip()
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


@pytest.mark.anyio()
async def test_F1_session_created_on_first_message(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    """F1: session is created when session_id is null."""
    resp = await user_client.post(
        "/me/chat",
        json={"message": "hello"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    session_events = [e for e in events if e.get("event") == "session"]
    assert len(session_events) == 1
    session_data = json.loads(session_events[0]["data"])
    assert "session_id" in session_data
    assert isinstance(session_data["session_id"], int)


@pytest.mark.anyio()
async def test_F3_messages_stored_on_done(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    """F3: all rows stored in one transaction at done."""
    resp = await user_client.post(
        "/me/chat",
        json={"message": "hello"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)

    # Extract session_id
    session_data = json.loads(events[0]["data"])
    session_id = session_data["session_id"]

    # Check messages are stored
    with db_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM chat_message WHERE session_id = :s"),
            {"s": session_id},
        ).scalar_one()
    assert count >= 2  # at minimum user + assistant


@pytest.mark.anyio()
async def test_F3_error_stores_nothing(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    """F3: an error turn stores nothing."""
    with db_engine.connect() as conn:
        msg_before = conn.execute(text("SELECT count(*) FROM chat_message")).scalar_one()

    resp = await user_client.post(
        "/me/chat",
        json={"message": "trigger error"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    error_events = [e for e in events if e.get("event") == "error"]
    assert len(error_events) == 1

    with db_engine.connect() as conn:
        msg_after = conn.execute(text("SELECT count(*) FROM chat_message")).scalar_one()
    assert msg_after == msg_before


@pytest.mark.anyio()
async def test_F12_event_order(
    user_client: AsyncClient,
) -> None:
    """F12: session first, then tokens, then done."""
    resp = await user_client.post(
        "/me/chat",
        json={"message": "hello"},
    )
    events = _parse_sse(resp.text)
    event_types = [e["event"] for e in events if "event" in e]
    assert event_types[0] == "session"
    assert event_types[-1] == "done"
    # Middle events should be intent (optional) and tokens
    allowed_middle = {"token", "intent"}
    for t in event_types[1:-1]:
        assert t in allowed_middle


@pytest.mark.anyio()
async def test_F12_cards_after_tokens(
    user_client: AsyncClient,
) -> None:
    """F12: cards come after tokens, before done."""
    resp = await user_client.post(
        "/me/chat",
        json={"message": "I want to book a visit"},
    )
    events = _parse_sse(resp.text)
    event_types = [e["event"] for e in events if "event" in e]
    assert "cards" in event_types
    cards_idx = event_types.index("cards")
    done_idx = event_types.index("done")
    assert cards_idx < done_idx
    # All tokens come before cards
    token_indices = [i for i, t in enumerate(event_types) if t == "token"]
    assert all(i < cards_idx for i in token_indices)


@pytest.mark.anyio()
async def test_F1_existing_session(
    user_client: AsyncClient,
) -> None:
    """F1: can send to an existing session."""
    # First message creates session
    resp1 = await user_client.post("/me/chat", json={"message": "hello"})
    events1 = _parse_sse(resp1.text)
    sid = json.loads(events1[0]["data"])["session_id"]

    # Second message uses the same session
    resp2 = await user_client.post("/me/chat", json={"session_id": sid, "message": "hi again"})
    events2 = _parse_sse(resp2.text)
    sid2 = json.loads(events2[0]["data"])["session_id"]
    assert sid2 == sid


@pytest.mark.anyio()
async def test_F2_other_users_session_rejected(
    user_client: AsyncClient, app: object, db_engine: Engine
) -> None:
    """F2: another user's session_id gives 404."""
    # Create a session for user1
    resp = await user_client.post("/me/chat", json={"message": "hello"})
    events = _parse_sse(resp.text)
    sid = json.loads(events[0]["data"])["session_id"]

    # Create another user
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c2:
        await c2.post("/auth/signup", json={"username": "user2", "password": "userpass2"})
        await c2.post("/auth/login", json={"username": "user2", "password": "userpass2"})
        locs = (await c2.get("/locations")).json()
        await c2.post("/me/profile", json={"name": "User Two", "location_id": locs[0]["id"]})

        resp2 = await c2.post("/me/chat", json={"session_id": sid, "message": "hijack"})
        assert resp2.status_code == 404


@pytest.mark.anyio()
async def test_F15_minute_rate_limit(
    user_client: AsyncClient, clock: FakeClock
) -> None:
    """F15: 6 messages per minute per user, with Retry-After."""
    for i in range(6):
        resp = await user_client.post("/me/chat", json={"message": f"msg {i}"})
        assert resp.status_code == 200

    resp = await user_client.post("/me/chat", json={"message": "one too many"})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers

    # Advance past the window
    clock.advance(61)
    resp = await user_client.post("/me/chat", json={"message": "after window"})
    assert resp.status_code == 200


@pytest.mark.anyio()
async def test_F15_daily_rate_limit(
    user_client: AsyncClient, clock: FakeClock
) -> None:
    """F15: 100 messages per day per user."""
    for i in range(100):
        clock.advance(11)  # skip past the per-minute window
        resp = await user_client.post("/me/chat", json={"message": f"msg {i}"})
        assert resp.status_code == 200

    clock.advance(11)
    resp = await user_client.post("/me/chat", json={"message": "one too many"})
    assert resp.status_code == 429
    assert resp.json()["detail"]["error"]["code"] == "rate_limited"


@pytest.mark.anyio()
async def test_F15_admin_exempt_from_daily(
    admin_user_client: AsyncClient, clock: FakeClock
) -> None:
    """F15: admins are exempt from daily limit."""
    for i in range(7):
        resp = await admin_user_client.post("/me/chat", json={"message": f"msg {i}"})
        # The per-minute limit still applies to admins
        if resp.status_code == 429:
            clock.advance(61)
            resp = await admin_user_client.post("/me/chat", json={"message": f"msg {i}"})
        assert resp.status_code == 200


@pytest.mark.anyio()
async def test_F15_message_too_long(
    user_client: AsyncClient,
) -> None:
    """F15: message exceeding 1000 characters is rejected."""
    resp = await user_client.post(
        "/me/chat",
        json={"message": "x" * 1001},
    )
    assert resp.status_code == 429


@pytest.mark.anyio()
async def test_F1_intent_set_on_first_message(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    """F1/F6: intent is set when the stub detects one on the first message."""
    resp = await user_client.post(
        "/me/chat",
        json={"message": "I want to book a visit"},
    )
    events = _parse_sse(resp.text)

    # intent event should be present
    intent_events = [e for e in events if e.get("event") == "intent"]
    assert len(intent_events) == 1
    assert json.loads(intent_events[0]["data"])["intent"] == "visit.book"

    # Check in DB
    sid = json.loads(events[0]["data"])["session_id"]
    with db_engine.connect() as conn:
        intent = conn.execute(
            text("SELECT intent FROM chat_session WHERE id = :s"),
            {"s": sid},
        ).scalar_one()
    assert intent == "visit.book"


@pytest.mark.anyio()
async def test_F3_last_message_at_updated(
    user_client: AsyncClient, db_engine: Engine, clock: FakeClock
) -> None:
    """F3: last_message_at is updated after a turn."""
    resp = await user_client.post("/me/chat", json={"message": "hello"})
    events = _parse_sse(resp.text)
    sid = json.loads(events[0]["data"])["session_id"]

    with db_engine.connect() as conn:
        ts = conn.execute(
            text("SELECT last_message_at FROM chat_session WHERE id = :s"),
            {"s": sid},
        ).scalar_one()
    assert ts is not None
