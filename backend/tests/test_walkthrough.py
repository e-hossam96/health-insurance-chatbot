from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings
from chatbot_ai.ingest import ingest
from chatbot_ai.ingest.index import collection_name, make_qdrant
from chatbot_ai.settings import AISettings
from testkit.ai_settings import settings_for
from testkit.fake_openai import (
    FakeOpenAI,
    ToolCallSpec,
    json_reply,
    run_fake_openai,
    text_reply,
    tool_reply,
)

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot")
POLICY_TEXT = (
    "Outpatient care. Dermatology and other specialist visits at network clinics are covered as outpatient visits "
    "with a co-pay of 50 EGP per visit.\n\nExclusions. Cosmetic dermatology is not covered."
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 12, 1, 8, 0, tzinfo=UTC)


@dataclass(frozen=True)
class World:
    derm: int
    cairo: int
    slots: list[int]
    kb_document: int


def _parse_sse(content: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    name = ""
    for line in content.splitlines():
        if line.startswith("event: "):
            name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            events.append((name, json.loads(line.removeprefix("data: "))))
    return events


def _seed(engine: Engine, kb_file: Path) -> World:
    def one(conn: object, sql: str, **params: object) -> int:
        value: int = conn.execute(text(sql + " RETURNING id"), params).scalar_one()  # type: ignore[attr-defined]
        return value

    with engine.begin() as conn:
        cairo = conn.execute(text("SELECT id FROM location WHERE name = 'TestCity'")).scalar_one()
        derm = one(conn, "INSERT INTO specialty (name) VALUES ('Dermatology')")
        clinic = one(conn, "INSERT INTO clinic (name, location_id) VALUES ('Cairo Clinic', :l)", l=cairo)
        cs = one(conn, "INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s)", c=clinic, s=derm)
        doctors = [one(conn, "INSERT INTO doctor (name, clinic_specialty_id) VALUES (:n, :cs)", n=name, cs=cs) for name in ("Dr. Sara Nabil", "Dr. Lina Fares")]
        slots = [
            one(conn, "INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, :t, 'available')", d=doctors[0], t="2026-12-15 10:00:00+00"),
            one(conn, "INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, :t, 'available')", d=doctors[1], t="2026-12-16 11:00:00+00"),
        ]
        admin = conn.execute(text("SELECT id FROM account WHERE username = 'admin1'")).scalar_one()
        kb_document = one(
            conn,
            "INSERT INTO kb_document (filename, file_type, file_size_bytes, storage_path, content_hash, status, uploaded_by) "
            "VALUES ('policy.txt', 'txt', :size, :path, :hash, 'ready', :admin)",
            size=len(POLICY_TEXT), path=str(kb_file), hash=uuid.uuid4().hex, admin=admin,
        )
    return World(derm=derm, cairo=cairo, slots=slots, kb_document=kb_document)


@pytest.fixture()
def fake() -> Iterator[FakeOpenAI]:
    with run_fake_openai() as server:
        yield server


@pytest.fixture()
def ai_settings(fake: FakeOpenAI) -> Iterator[AISettings]:
    settings = settings_for(fake.base_url, ai_embedding_model=f"walk-{uuid.uuid4().hex[:10]}")
    yield settings

    async def drop() -> None:
        client = make_qdrant(settings)
        if await client.collection_exists(collection_name(settings)):
            await client.delete_collection(collection_name(settings))
        await client.close()

    asyncio.run(drop())


async def _signed_in(app: FastAPI) -> AsyncClient:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="https://test")
    await client.post("/auth/signup", json={"username": "mona", "password": "monapass1"})
    await client.post("/auth/login", json={"username": "mona", "password": "monapass1"})
    locations = (await client.get("/locations")).json()
    await client.post("/me/profile", json={"name": "Mona", "location_id": locations[0]["id"]})
    return client


@pytest.fixture()
async def app_and_world(
    _migrate_fresh: None, db_engine: Engine, ai_settings: AISettings, tmp_path: Path
) -> AsyncIterator[tuple[FastAPI, World]]:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    kb_file = tmp_path / "policy.txt"
    kb_file.write_text(POLICY_TEXT, encoding="utf-8")
    world = _seed(db_engine, kb_file)
    await asyncio.to_thread(ingest, world.kb_document, str(kb_file), "txt", ai_settings)
    settings = Settings(database_url=TEST_DB_URL, kb_storage_dir=str(tmp_path))  # type: ignore[call-arg]
    app = create_app(settings, ai_settings=ai_settings, ai_from_env=False)
    app.state.clock = FixedClock()
    async with app.router.lifespan_context(app):
        yield app, world


@pytest.mark.anyio()
async def test_walkthrough_booking_card_click_and_knowledge_question(
    app_and_world: tuple[FastAPI, World], fake: FakeOpenAI, db_engine: Engine
) -> None:
    app, world = app_and_world
    client = await _signed_in(app)
    try:
        fake.queue(json_reply({"intent": "visit.book"}), json_reply({"intent": "qa.kb"}), model="router-model")
        fake.queue(
            tool_reply(ToolCallSpec("list_specialties", {}, id="t1")),
            tool_reply(ToolCallSpec("recommend_doctors", {"specialty_id": world.derm}, id="t2")),
            text_reply("Dr. Sara Nabil at Cairo Clinic on Tue 15 Dec, 10:00 UTC, or Dr. Lina Fares on Wed 16 Dec, 11:00 UTC."),
            model="chat-model",
        )
        first = await client.post("/me/chat", json={"message": "I need a dermatologist"})
        events = _parse_sse(first.text)
        names = [name for name, _ in events]
        assert names[0] == "session" and names[1] == "intent" and names[-2:] == ["cards", "done"]
        assert events[1][1] == {"intent": "visit.book"}
        session_id = int(str(events[0][1]["session_id"]))
        cards = events[-2][1]
        assert cards["type"] == "doctors"
        items = cards["items"]
        assert isinstance(items, list)
        assert [item["slot_id"] for item in items] == world.slots
        assert items[0]["start_at"] == "2026-12-15T10:00:00Z"

        with db_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT role, tool_name, content FROM chat_message WHERE session_id = :s ORDER BY id"), {"s": session_id}
            ).all()
            intent = conn.execute(text("SELECT intent FROM chat_session WHERE id = :s"), {"s": session_id}).scalar_one()
        assert [(r[0], r[1]) for r in rows] == [
            ("user", None),
            ("assistant", None),
            ("tool", "list_specialties"),
            ("assistant", None),
            ("tool", "recommend_doctors"),
            ("assistant", None),
        ]
        assert intent == "visit.book"

        booked = await client.post("/me/visits", json={"session_id": session_id, "slot_id": world.slots[0]})
        assert booked.status_code == 201

        fake.queue(json_reply({"standalone": "Is a dermatology visit covered and what is the co-pay?", "alternates": ["dermatology co-pay", "specialist visit cost"]}), model="rewrite-model")
        fake.queue(text_reply("Yes. Dermatology visits are outpatient visits with a co-pay of 50 EGP."), model="chat-model")
        second = await client.post("/me/chat", json={"session_id": session_id, "message": "Is that covered? What's the co-pay?"})
        second_events = _parse_sse(second.text)
        assert [name for name, _ in second_events if name not in ("token",)] == ["session", "done"]
        assert "".join(str(data["text"]) for name, data in second_events if name == "token") == "Yes. Dermatology visits are outpatient visits with a co-pay of 50 EGP."

        answer_request = [r for r in fake.chat_requests if r["model"] == "chat-model"][-1]
        system_prompt = answer_request["messages"][0]["content"]
        assert "co-pay of 50 EGP per visit" in system_prompt
        assert "Mona" in system_prompt and "TestCity" in system_prompt
        assert any(m.get("role") == "tool" for m in answer_request["messages"]), "the history of turn 1 reaches the agent (I4)"

        transcript = (await client.get(f"/me/sessions/{session_id}/messages")).json()
        contents = [(m["role"], m["content"]) for m in transcript]
        assert contents[0] == ("user", "I need a dermatologist")
        assert contents[1][0] == "assistant" and "Dr. Sara Nabil" in contents[1][1]
        assert contents[-2] == ("user", "Is that covered? What's the co-pay?")
        assert contents[-1] == ("assistant", "Yes. Dermatology visits are outpatient visits with a co-pay of 50 EGP.")
        assert all(role in ("user", "assistant") and content for role, content in contents)
        with db_engine.connect() as conn:
            search_rows = conn.execute(
                text("SELECT count(*) FROM chat_message WHERE session_id = :s AND tool_name = 'search_kb'"), {"s": session_id}
            ).scalar_one()
        assert search_rows == 1
        with db_engine.connect() as conn:
            label = conn.execute(text("SELECT intent FROM chat_session WHERE id = :s"), {"s": session_id}).scalar_one()
        assert label == "visit.book", "F6: the label never changes after it is set"
        assert fake.pending() == 0
    finally:
        await client.aclose()


@pytest.mark.anyio()
async def test_without_ai_settings_a_turn_fails_cleanly(_migrate_fresh: None, tmp_path: Path, db_engine: Engine) -> None:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    settings = Settings(database_url=TEST_DB_URL, kb_storage_dir=str(tmp_path))  # type: ignore[call-arg]
    app = create_app(settings, ai_settings=None, ai_from_env=False)
    client = await _signed_in(app)
    try:
        response = await client.post("/me/chat", json={"message": "hello"})
        events = _parse_sse(response.text)
        assert [name for name, _ in events] == ["session", "error"]
        with db_engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM chat_session")).scalar_one() == 0
    finally:
        await client.aclose()
