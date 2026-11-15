from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

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
async def user_client(app: object) -> AsyncClient:
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
async def test_F11_list_sessions_ordered(user_client: AsyncClient, clock: FakeClock) -> None:
    resp1 = await user_client.post("/me/chat", json={"message": "first session"})
    sid1 = json.loads(_parse_sse(resp1.text)[0]["data"])["session_id"]

    clock.advance(10)
    resp2 = await user_client.post("/me/chat", json={"message": "second session"})
    sid2 = json.loads(_parse_sse(resp2.text)[0]["data"])["session_id"]

    resp = await user_client.get("/me/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    assert len(sessions) == 2
    # Most recent first
    assert sessions[0]["id"] == sid2
    assert sessions[1]["id"] == sid1


@pytest.mark.anyio()
async def test_F11_session_has_first_message(user_client: AsyncClient) -> None:
    resp = await user_client.post("/me/chat", json={"message": "Hello there, I need help"})
    sid = json.loads(_parse_sse(resp.text)[0]["data"])["session_id"]

    sessions = (await user_client.get("/me/sessions")).json()
    session = next(s for s in sessions if s["id"] == sid)
    assert session["first_user_message"] is not None
    assert "Hello there" in session["first_user_message"]


@pytest.mark.anyio()
async def test_F11_messages_filter(user_client: AsyncClient) -> None:
    # Use a tool call scenario to generate tool_call and tool rows
    resp = await user_client.post("/me/chat", json={"message": "I want to book a visit"})
    sid = json.loads(_parse_sse(resp.text)[0]["data"])["session_id"]

    msg_resp = await user_client.get(f"/me/sessions/{sid}/messages")
    assert msg_resp.status_code == 200
    messages = msg_resp.json()

    # Should only have user and final assistant (no tool, no empty assistant)
    for m in messages:
        assert m["role"] in ("user", "assistant")
        if m["role"] == "assistant":
            assert m["content"] != ""


@pytest.mark.anyio()
async def test_F11_other_users_session_rejected(
    user_client: AsyncClient, app: object
) -> None:
    resp = await user_client.post("/me/chat", json={"message": "hello"})
    sid = json.loads(_parse_sse(resp.text)[0]["data"])["session_id"]

    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="https://test",
    ) as c2:
        await c2.post("/auth/signup", json={"username": "user2", "password": "userpass2"})
        await c2.post("/auth/login", json={"username": "user2", "password": "userpass2"})
        locs = (await c2.get("/locations")).json()
        await c2.post("/me/profile", json={"name": "User Two", "location_id": locs[0]["id"]})

        msg_resp = await c2.get(f"/me/sessions/{sid}/messages")
        assert msg_resp.status_code == 404
