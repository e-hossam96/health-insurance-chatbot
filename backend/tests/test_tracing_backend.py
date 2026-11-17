from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend.app import create_app
from backend.config import Settings
from chatbot_ai.tracing import LangfuseTracer
from testkit.ai_settings import settings_for
from testkit.fake_openai import FakeOpenAI, json_reply, run_fake_openai, text_reply

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot")


@pytest.fixture()
def fake() -> Iterator[FakeOpenAI]:
    with run_fake_openai() as server:
        yield server


@pytest.fixture()
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture()
async def traced(_clean_database: None, fake: FakeOpenAI, exporter: InMemorySpanExporter, tmp_path: Path) -> AsyncIterator[tuple[AsyncClient, Langfuse]]:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    app = create_app(Settings(database_url=TEST_DB_URL, kb_storage_dir=str(tmp_path)), ai_settings=settings_for(fake.base_url), ai_from_env=False)  # type: ignore[call-arg]
    langfuse = Langfuse(public_key=f"pk-{uuid.uuid4().hex}", secret_key="sk-test", host="http://127.0.0.1:9", span_exporter=exporter, flush_at=1)
    app.state.role_clients._tracer = LangfuseTracer(langfuse)
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        await client.post("/auth/signup", json={"username": "mona", "password": "monapass1"})
        await client.post("/auth/login", json={"username": "mona", "password": "monapass1"})
        locations = (await client.get("/locations")).json()
        await client.post("/me/profile", json={"name": "Mona", "location_id": locations[0]["id"]})
        yield client, langfuse
    langfuse.shutdown()


@pytest.mark.anyio()
async def test_F7_a_chat_turn_through_the_api_is_traced_under_the_chat_session_id(
    traced: tuple[AsyncClient, Langfuse], fake: FakeOpenAI, exporter: InMemorySpanExporter
) -> None:
    client, langfuse = traced
    fake.queue(json_reply({"intent": "other"}), json_reply({"intent": "other"}), model="router-model")
    fake.queue(text_reply("Hello Mona"), text_reply("Hello again"), model="chat-model")
    first = await client.post("/me/chat", json={"message": "hi"})
    session_id = json.loads(first.text.split("data: ", 1)[1].split("\n", 1)[0])["session_id"]
    await client.post("/me/chat", json={"session_id": session_id, "message": "again"})
    langfuse.flush()

    spans = list(exporter.get_finished_spans())
    sessions = {value for span in spans for key, value in (span.attributes or {}).items() if "session" in key}
    assert sessions == {f"chat-{session_id}"}
    roots = [span for span in spans if span.name == "chat turn"]
    assert len(roots) == 2
    assert len({span.context.trace_id for span in roots if span.context}) == 2, "each turn is its own trace"
    assert all(span.parent is None for span in roots), "the turn span is the trace root"
    assert all("hi" in str((span.attributes or {}).get("langfuse.observation.input")) for span in roots[:1])
