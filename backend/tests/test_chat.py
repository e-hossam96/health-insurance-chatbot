from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings, get_settings
from chatbot_ai.interface import Done, HistoryRow, Token, TurnEvent, TurnRequest
from chatbot_ai.stub import run_stub_turn

TEST_DB_URL = get_settings().database_url


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: int) -> None:
        self._now += timedelta(seconds=seconds)

    def set(self, now: datetime) -> None:
        self._now = now


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 12, 1, 8, 0, tzinfo=UTC))


@pytest.fixture()
def app(_clean_database: None, clock: FakeClock) -> object:
    settings = Settings()  # type: ignore[call-arg]
    application = create_app(settings)
    application.state.clock = clock  # type: ignore[union-attr]
    application.state.turn_runner = run_stub_turn  # type: ignore[union-attr]
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
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c:
        await c.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
        await c.post("/auth/mode", json={"mode": "user"})
        yield c  # type: ignore[misc]


def _session_count(db_engine: Engine) -> int:
    with db_engine.connect() as conn:
        count: int = conn.execute(text("SELECT count(*) FROM chat_session")).scalar_one()
        return count


def _stored_rows(db_engine: Engine, session_id: int) -> list[tuple[str, str, Any, str | None]]:
    with db_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT role, content, tool_calls, tool_call_id FROM chat_message WHERE session_id = :s ORDER BY id"),
            {"s": session_id},
        ).all()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


def _last_message_at(db_engine: Engine, session_id: int) -> datetime:
    with db_engine.connect() as conn:
        value: datetime = conn.execute(
            text("SELECT last_message_at FROM chat_session WHERE id = :s"), {"s": session_id}
        ).scalar_one()
        return value


def _parse_sse(content: str) -> list[dict[str, str]]:
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
    assert _session_count(db_engine) == 0
    resp = await user_client.post("/me/chat", json={"message": "hello"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [e["event"] for e in events].count("session") == 1
    sid = json.loads(events[0]["data"])["session_id"]

    with db_engine.connect() as conn:
        owner = conn.execute(
            text(
                "SELECT a.username FROM chat_session s JOIN profile p ON p.id = s.profile_id "
                "JOIN account a ON a.id = p.account_id WHERE s.id = :s"
            ),
            {"s": sid},
        ).scalar_one()
    assert owner == "user1"
    assert _session_count(db_engine) == 1

    again = await user_client.post("/me/chat", json={"session_id": sid, "message": "and again"})
    assert json.loads(_parse_sse(again.text)[0]["data"])["session_id"] == sid
    assert _session_count(db_engine) == 1


@pytest.mark.anyio()
async def test_F3_messages_stored_on_done(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    resp = await user_client.post("/me/chat", json={"message": "I want to book a visit"})
    assert resp.status_code == 200
    session_id = json.loads(_parse_sse(resp.text)[0]["data"])["session_id"]

    rows = _stored_rows(db_engine, session_id)
    assert [(r[0], r[2] is not None, r[3] is not None) for r in rows] == [
        ("user", False, False),
        ("assistant", True, False),
        ("tool", False, True),
        ("assistant", False, False),
    ]
    assert rows[0][1] == "I want to book a visit"
    assert rows[3][1] == "Here are the available options for you."
    assert rows[2][3] == rows[1][2][0]["id"]


@pytest.mark.anyio()
async def test_F3_error_stores_nothing(
    user_client: AsyncClient, db_engine: Engine
) -> None:
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
    resp = await user_client.post("/me/chat", json={"message": "hello"})
    sid = json.loads(_parse_sse(resp.text)[0]["data"])["session_id"]
    rows_before = len(_stored_rows(db_engine, sid))

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
        assert resp2.json()["detail"]["error"]["code"] == "not_found"

    assert len(_stored_rows(db_engine, sid)) == rows_before
    assert _session_count(db_engine) == 1


@pytest.mark.anyio()
async def test_F15_minute_rate_limit(
    user_client: AsyncClient, clock: FakeClock
) -> None:
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
    for i in range(105):
        clock.advance(11)
        resp = await admin_user_client.post("/me/chat", json={"message": f"msg {i}"})
        assert resp.status_code == 200, f"admin message {i} was limited"


@pytest.mark.anyio()
async def test_F15_message_too_long(
    user_client: AsyncClient, clock: FakeClock
) -> None:
    at_limit = await user_client.post("/me/chat", json={"message": "x" * 1000})
    assert at_limit.status_code == 200

    clock.advance(11)
    multibyte_at_limit = await user_client.post("/me/chat", json={"message": "\u00e9" * 1000})
    assert multibyte_at_limit.status_code == 200

    clock.advance(11)
    over = await user_client.post("/me/chat", json={"message": "x" * 1001})
    assert over.status_code == 422
    assert over.json()["detail"]["error"] == {"code": "validation_error", "message": "Message exceeds 1000 characters."}
    assert "Retry-After" not in over.headers


@pytest.mark.anyio()
async def test_F1_intent_set_on_first_message(
    user_client: AsyncClient, db_engine: Engine
) -> None:
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
    resp = await user_client.post("/me/chat", json={"message": "hello"})
    sid = json.loads(_parse_sse(resp.text)[0]["data"])["session_id"]
    assert _last_message_at(db_engine, sid) == clock.now()

    clock.advance(120)
    await user_client.post("/me/chat", json={"session_id": sid, "message": "second"})
    second_turn_at = clock.now()
    assert _last_message_at(db_engine, sid) == second_turn_at

    clock.advance(120)
    failed = await user_client.post("/me/chat", json={"session_id": sid, "message": "trigger error"})
    assert any(e.get("event") == "error" for e in _parse_sse(failed.text))
    assert _last_message_at(db_engine, sid) == second_turn_at


@pytest.mark.anyio()
async def test_completed_slow_stream_stores_rows(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    resp = await user_client.post("/me/chat", json={"message": "slow stream test"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    assert [e["event"] for e in events].count("done") == 1
    sid = json.loads(events[0]["data"])["session_id"]
    assert [r[0] for r in _stored_rows(db_engine, sid)] == ["user", "assistant"]


@pytest.mark.anyio()
async def test_F12_cards_not_stored_in_messages(
    user_client: AsyncClient, db_engine: Engine
) -> None:
    resp = await user_client.post("/me/chat", json={"message": "I want to book a visit"})
    events = _parse_sse(resp.text)
    cards = next(json.loads(e["data"]) for e in events if e.get("event") == "cards")
    assert cards["type"] == "doctors"
    for item in cards["items"]:
        assert set(item) == {"slot_id", "doctor_name", "specialty", "clinic", "location", "start_at"}

    sid = json.loads(events[0]["data"])["session_id"]
    with db_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT content, coalesce(tool_calls::text, '') FROM chat_message WHERE session_id = :s"),
            {"s": sid},
        ).all()
    card_payload = json.dumps(cards)
    card_items = json.dumps(cards["items"])
    for content, tool_calls in stored:
        assert card_payload not in content and card_items not in content
        assert '"type": "doctors"' not in content and '"type": "doctors"' not in tool_calls
    transcript = (await user_client.get(f"/me/sessions/{sid}/messages")).json()
    assert [m["role"] for m in transcript] == ["user", "assistant"]
    assert all(set(m) == {"id", "session_id", "role", "content"} for m in transcript)


@pytest.mark.anyio()
async def test_C8_timestamps_are_utc(
    user_client: AsyncClient, clock: FakeClock
) -> None:
    resp = await user_client.post("/me/chat", json={"message": "I want to book a visit"})
    assert resp.status_code == 200
    cards = next(json.loads(e["data"]) for e in _parse_sse(resp.text) if e.get("event") == "cards")
    for item in cards["items"]:
        assert datetime.fromisoformat(item["start_at"]).utcoffset() == timedelta(0)

    sessions = (await user_client.get("/me/sessions")).json()
    assert len(sessions) == 1
    for field in ("created_at", "last_message_at"):
        parsed = datetime.fromisoformat(sessions[0][field])
        assert parsed.utcoffset() == timedelta(0), field
    assert datetime.fromisoformat(sessions[0]["last_message_at"]) == clock.now()


@pytest.mark.anyio()
async def test_C8_time_zone_headers_change_nothing(user_client: AsyncClient) -> None:
    await user_client.post("/me/chat", json={"message": "hello"})
    plain = (await user_client.get("/me/sessions")).json()
    zoned = (
        await user_client.get(
            "/me/sessions",
            headers={"Time-Zone": "Asia/Tokyo", "X-Timezone": "America/New_York", "Accept-Language": "ja-JP"},
        )
    ).json()
    assert zoned == plain


class ScriptedTurn:
    def __init__(self, events: list[TurnEvent], fail_after: bool = False) -> None:
        self.events = events
        self.fail_after = fail_after
        self.requests: list[TurnRequest] = []

    async def __call__(self, request: TurnRequest) -> AsyncIterator[TurnEvent]:
        self.requests.append(request)
        for event in self.events:
            yield event
        if self.fail_after:
            raise RuntimeError("model call failed mid-turn")


def _reply(message: str, text_reply: str = "ok") -> Done:
    return Done(new_rows=[HistoryRow(role="user", content=message), HistoryRow(role="assistant", content=text_reply)])


@pytest.mark.anyio()
async def test_F1_page_load_creates_no_session(user_client: AsyncClient, db_engine: Engine) -> None:
    assert (await user_client.get("/me/sessions")).json() == []
    assert (await user_client.get("/me/sessions/999/messages")).status_code == 404
    assert (await user_client.get("/me/visits")).status_code == 200
    assert _session_count(db_engine) == 0


@pytest.mark.anyio()
async def test_F2_nonexistent_session_rejected(user_client: AsyncClient, db_engine: Engine) -> None:
    resp = await user_client.post("/me/chat", json={"session_id": 999999, "message": "hello"})
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "not_found"
    assert _session_count(db_engine) == 0


@pytest.mark.anyio()
async def test_F3_failure_after_tokens_stores_nothing(
    app: Any, user_client: AsyncClient, db_engine: Engine, clock: FakeClock
) -> None:
    first = await user_client.post("/me/chat", json={"message": "hello"})
    sid = json.loads(_parse_sse(first.text)[0]["data"])["session_id"]
    rows_before = _stored_rows(db_engine, sid)
    stamp_before = _last_message_at(db_engine, sid)

    app.state.turn_runner = ScriptedTurn([Token(text="partial ", elapsed=0.0)], fail_after=True)
    clock.advance(60)
    resp = await user_client.post("/me/chat", json={"session_id": sid, "message": "this will fail"})

    events = _parse_sse(resp.text)
    assert [e["event"] for e in events] == ["session", "token", "error"]
    assert json.loads(events[-1]["data"]) == {"code": "turn_error", "message": "Something went wrong."}
    assert _stored_rows(db_engine, sid) == rows_before
    assert _last_message_at(db_engine, sid) == stamp_before


@pytest.mark.anyio()
async def test_F3_rows_are_one_transaction(
    app: Any, user_client: AsyncClient, db_engine: Engine, clock: FakeClock
) -> None:
    first = await user_client.post("/me/chat", json={"message": "hello"})
    sid = json.loads(_parse_sse(first.text)[0]["data"])["session_id"]
    rows_before = _stored_rows(db_engine, sid)
    stamp_before = _last_message_at(db_engine, sid)

    broken_done = Done(
        new_rows=[
            HistoryRow(role="user", content="book please"),
            HistoryRow(
                role="assistant",
                content="",
                tool_calls=[{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
            ),
            HistoryRow(role="tool", content="bad \x00 byte", tool_call_id="c1", tool_name="f"),
            HistoryRow(role="assistant", content="done"),
        ]
    )
    app.state.turn_runner = ScriptedTurn([Token(text="done", elapsed=0.0), broken_done])
    clock.advance(60)
    resp = await user_client.post("/me/chat", json={"session_id": sid, "message": "book please"})

    assert [e["event"] for e in _parse_sse(resp.text)][-1] == "error"
    assert _stored_rows(db_engine, sid) == rows_before
    assert _last_message_at(db_engine, sid) == stamp_before


@pytest.mark.anyio()
async def test_F4_F10_history_comes_from_stored_rows(
    app: Any, user_client: AsyncClient, db_engine: Engine
) -> None:
    first = await user_client.post("/me/chat", json={"message": "I want to book a visit"})
    sid = json.loads(_parse_sse(first.text)[0]["data"])["session_id"]

    capture = ScriptedTurn([_reply("next")])
    app.state.turn_runner = capture
    await user_client.post("/me/chat", json={"session_id": sid, "message": "next"})

    history = capture.requests[0].history
    stored = _stored_rows(db_engine, sid)[:4]
    assert [(h.role, h.content, h.tool_call_id) for h in history] == [(r[0], r[1], r[3]) for r in stored]
    assert history[1].tool_calls == stored[1][2]
    assert capture.requests[0].message == "next"


@pytest.mark.anyio()
async def test_F4_history_is_last_40_rows_from_a_user_row(
    app: Any, user_client: AsyncClient, db_engine: Engine
) -> None:
    first = await user_client.post("/me/chat", json={"message": "hello"})
    sid = json.loads(_parse_sse(first.text)[0]["data"])["session_id"]
    with db_engine.connect() as conn:
        for i in range(50):
            conn.execute(
                text("INSERT INTO chat_message (session_id, role, content) VALUES (:s, :r, :c)"),
                {"s": sid, "r": "assistant" if i % 2 == 0 else "user", "c": f"row {i}"},
            )
        conn.commit()

    capture = ScriptedTurn([_reply("latest")])
    app.state.turn_runner = capture
    await user_client.post("/me/chat", json={"session_id": sid, "message": "latest"})

    history = capture.requests[0].history
    assert len(history) == 39
    assert history[0].role == "user"
    assert history[0].content == "row 11"
    assert history[-1].content == "row 49"


@pytest.mark.anyio()
async def test_F4_stored_tool_result_is_capped(
    app: Any, user_client: AsyncClient, db_engine: Engine
) -> None:
    from chatbot_ai.context import STORED_TOOL_RESULT_MAX_LEN, TOOL_RESULT_PLACEHOLDER

    huge = "y" * (STORED_TOOL_RESULT_MAX_LEN * 3)
    app.state.turn_runner = ScriptedTurn([
        Done(
            new_rows=[
                HistoryRow(role="user", content="q"),
                HistoryRow(
                    role="assistant",
                    content="",
                    tool_calls=[{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
                ),
                HistoryRow(role="tool", content=huge, tool_call_id="c1", tool_name="f"),
                HistoryRow(role="assistant", content="a"),
            ]
        )
    ])
    resp = await user_client.post("/me/chat", json={"message": "q"})
    sid = json.loads(_parse_sse(resp.text)[0]["data"])["session_id"]

    tool_content = _stored_rows(db_engine, sid)[2][1]
    assert tool_content == huge[:STORED_TOOL_RESULT_MAX_LEN] + TOOL_RESULT_PLACEHOLDER


@pytest.mark.anyio()
async def test_F15_daily_cap_is_per_utc_date_not_rolling(
    user_client: AsyncClient, clock: FakeClock
) -> None:
    clock.set(datetime(2026, 12, 1, 23, 35, tzinfo=UTC))
    for i in range(100):
        clock.advance(11)
        assert (await user_client.post("/me/chat", json={"message": f"m{i}"})).status_code == 200
    clock.advance(11)
    assert (await user_client.post("/me/chat", json={"message": "cap"})).status_code == 429

    clock.set(datetime(2026, 12, 2, 0, 0, 1, tzinfo=UTC))
    assert (await user_client.post("/me/chat", json={"message": "new day"})).status_code == 200


@pytest.mark.anyio()
async def test_F15_failed_turns_count_toward_the_limit(user_client: AsyncClient) -> None:
    for _ in range(6):
        resp = await user_client.post("/me/chat", json={"message": "trigger error"})
        assert resp.status_code == 200
        assert any(e.get("event") == "error" for e in _parse_sse(resp.text))
    blocked = await user_client.post("/me/chat", json={"message": "hello"})
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["error"]["code"] == "rate_limited"


@pytest.mark.anyio()
async def test_F15_limits_are_per_user(user_client: AsyncClient, app: object) -> None:
    for i in range(6):
        await user_client.post("/me/chat", json={"message": f"m{i}"})
    assert (await user_client.post("/me/chat", json={"message": "over"})).status_code == 429

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c2:
        await c2.post("/auth/signup", json={"username": "user2", "password": "userpass2"})
        await c2.post("/auth/login", json={"username": "user2", "password": "userpass2"})
        locs = (await c2.get("/locations")).json()
        await c2.post("/me/profile", json={"name": "User Two", "location_id": locs[0]["id"]})
        assert (await c2.post("/me/chat", json={"message": "hi"})).status_code == 200


@pytest.mark.anyio()
async def test_F3_F16_a_failed_first_turn_leaves_no_session(user_client: AsyncClient, db_engine: Engine) -> None:
    resp = await user_client.post("/me/chat", json={"message": "trigger error"})
    events = _parse_sse(resp.text)
    assert (events[0]["event"], events[-1]["event"]) == ("session", "error")
    assert _session_count(db_engine) == 0
    assert (await user_client.get("/me/sessions")).json() == []


@pytest.mark.anyio()
async def test_F3_a_failed_turn_in_an_existing_session_keeps_the_session(user_client: AsyncClient, db_engine: Engine) -> None:
    first = await user_client.post("/me/chat", json={"message": "hello"})
    sid = json.loads(_parse_sse(first.text)[0]["data"])["session_id"]
    failed = await user_client.post("/me/chat", json={"session_id": sid, "message": "trigger error"})
    assert _parse_sse(failed.text)[-1]["event"] == "error"
    assert _session_count(db_engine) == 1
    assert [r[0] for r in _stored_rows(db_engine, sid)] == ["user", "assistant"]
