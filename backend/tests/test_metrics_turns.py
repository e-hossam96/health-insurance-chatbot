from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app import create_app
from backend.config import Settings
from chatbot_ai.interface import (
    Done,
    HistoryRow,
    Timings,
    Token,
    TurnEvent,
    TurnRequest,
    Usage,
)
from chatbot_ai.stub import run_stub_turn
from testkit.ai_settings import settings_for
from testkit.fake_openai import FakeOpenAI, json_reply, run_fake_openai, text_reply
from testkit.metrics import label_sets, metric_value

TEST_DB_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot")
ALLOWED_LABELS = {
    "outcome": {"ok", "error", "cancelled", "failed", "conflict", "rejected"},
    "agent": {"scheduling", "complaints", "knowledge", "responder", "unknown"},
    "stage": {"classify", "rewrite", "embed", "search", "rerank", "generate"},
    "kind": {"prompt", "completion"},
    "limit": {"chat_minute", "chat_daily", "message_length", "signup", "login"},
    "action": {"book", "cancel", "complaint"},
    "model": set(),
    "tool": set(),
}
OUR_PREFIXES = ("chat_", "kb_", "rate_limit_", "signups", "card_actions", "http_")


class FixedClock:
    def __init__(self) -> None:
        self.now_value = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.now_value


@pytest.fixture()
def fake() -> Iterator[FakeOpenAI]:
    with run_fake_openai() as server:
        yield server


@pytest.fixture()
async def client(_migrate_fresh: None, fake: FakeOpenAI, tmp_path: Path) -> AsyncIterator[AsyncClient]:
    from scripts.create_admin import create_admin

    create_admin(TEST_DB_URL, "admin1", "adminpass1", "Admin One", "TestCity")
    settings = Settings(database_url=TEST_DB_URL, kb_storage_dir=str(tmp_path))  # type: ignore[call-arg]
    app = create_app(settings, ai_settings=settings_for(fake.base_url), ai_from_env=False)
    app.state.clock = FixedClock()
    async with app.router.lifespan_context(app), AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        await c.post("/auth/signup", json={"username": "mona", "password": "monapass1"})
        await c.post("/auth/login", json={"username": "mona", "password": "monapass1"})
        locations = (await c.get("/locations")).json()
        await c.post("/me/profile", json={"name": "Mona", "location_id": locations[0]["id"]})
        c.app = app  # type: ignore[attr-defined]
        yield c


async def _metrics(client: AsyncClient) -> str:
    response = await client.get("/metrics")
    assert response.status_code == 200
    return response.text


@pytest.mark.anyio()
async def test_H2_H3_a_turn_on_the_fake_server_records_the_turn_metrics(client: AsyncClient, fake: FakeOpenAI) -> None:
    before = await _metrics(client)
    fake.queue(json_reply({"intent": "other"}), model="router-model")
    fake.queue(text_reply("Hello Mona, welcome back", prompt_tokens=40, completion_tokens=5), model="chat-model")
    response = await client.post("/me/chat", json={"message": "hi"})
    assert '"done"' in response.text or "event: done" in response.text
    after = await _metrics(client)

    def delta(name: str, labels: dict[str, str] | None = None) -> float:
        return metric_value(after, name, labels) - metric_value(before, name, labels)

    assert delta("chat_turns_total", {"outcome": "ok"}) == 1
    assert delta("chat_turns_by_agent_total", {"agent": "responder"}) == 1
    assert delta("chat_tokens_total", {"kind": "prompt"}) == 40 + 10
    assert delta("chat_tokens_total", {"kind": "completion"}) == 5 + 2
    assert delta("chat_ttft_seconds_count") == 1
    assert delta("chat_llm_duration_seconds_count") == 1
    assert delta("chat_turn_duration_seconds_count") == 1
    assert delta("chat_stage_duration_seconds_count", {"stage": "classify"}) == 1
    assert delta("chat_chunk_gap_seconds_count") == 3


@pytest.mark.anyio()
async def test_H3_a_failed_turn_counts_as_error(client: AsyncClient) -> None:
    client.app.state.turn_runner = run_stub_turn  # type: ignore[attr-defined]
    before = await _metrics(client)
    await client.post("/me/chat", json={"message": "trigger error"})
    after = await _metrics(client)
    assert metric_value(after, "chat_turns_total", {"outcome": "error"}) - metric_value(before, "chat_turns_total", {"outcome": "error"}) == 1
    assert metric_value(after, "chat_turns_total", {"outcome": "ok"}) == metric_value(before, "chat_turns_total", {"outcome": "ok"})


@pytest.mark.anyio()
async def test_H3_rate_limit_rejections_are_counted_by_limit_type(client: AsyncClient) -> None:
    client.app.state.turn_runner = run_stub_turn  # type: ignore[attr-defined]
    before = await _metrics(client)
    assert (await client.post("/me/chat", json={"message": "x" * 1001})).status_code == 422
    for i in range(6):
        await client.post("/me/chat", json={"message": f"m{i}"})
    assert (await client.post("/me/chat", json={"message": "over"})).status_code == 429
    after = await _metrics(client)
    for limit in ("message_length", "chat_minute"):
        assert metric_value(after, "rate_limit_rejections_total", {"limit": limit}) - metric_value(before, "rate_limit_rejections_total", {"limit": limit}) == 1


@pytest.mark.anyio()
async def test_H3_signups_and_card_actions_are_counted_at_the_endpoint(client: AsyncClient, db_engine: Engine) -> None:
    before = await _metrics(client)
    async with AsyncClient(transport=ASGITransport(app=client.app), base_url="https://test") as other:  # type: ignore[attr-defined]
        assert (await other.post("/auth/signup", json={"username": "newbie", "password": "newbiepass1"})).status_code == 201
    with db_engine.begin() as conn:
        location = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        clinic = conn.execute(text("INSERT INTO clinic (name, location_id) VALUES ('C', :l) RETURNING id"), {"l": location}).scalar_one()
        specialty = conn.execute(text("INSERT INTO specialty (name) VALUES ('S') RETURNING id")).scalar_one()
        cs = conn.execute(text("INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s) RETURNING id"), {"c": clinic, "s": specialty}).scalar_one()
        doctor = conn.execute(text("INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr', :cs) RETURNING id"), {"cs": cs}).scalar_one()
        slot = conn.execute(text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-15 10:00+00', 'available') RETURNING id"), {"d": doctor}).scalar_one()
        profile = conn.execute(text("SELECT p.id FROM profile p JOIN account a ON a.id = p.account_id WHERE a.username = 'mona'")).scalar_one()
        session_id = conn.execute(text("INSERT INTO chat_session (profile_id) VALUES (:p) RETURNING id"), {"p": profile}).scalar_one()
    assert (await client.post("/me/visits", json={"session_id": session_id, "slot_id": slot})).status_code == 201
    assert (await client.post("/me/visits", json={"session_id": session_id, "slot_id": slot})).status_code == 409
    after = await _metrics(client)

    def delta(name: str, labels: dict[str, str] | None = None) -> float:
        return metric_value(after, name, labels) - metric_value(before, name, labels)

    assert delta("signups_total") == 1
    assert delta("card_actions_total", {"action": "book", "outcome": "ok"}) == 1
    assert delta("card_actions_total", {"action": "book", "outcome": "conflict"}) == 1


@pytest.mark.anyio()
async def test_H4_labels_are_small_fixed_sets_without_ids(client: AsyncClient, fake: FakeOpenAI, db_engine: Engine) -> None:
    fake.queue(json_reply({"intent": "other"}), model="router-model")
    fake.queue(text_reply("Hello"), model="chat-model")
    await client.post("/me/chat", json={"message": "hi"})
    await client.get("/me/sessions/424242/messages")
    world = _seed_slot_and_session(db_engine)
    await client.post("/me/visits", json={"session_id": world[1], "slot_id": world[0]})
    await _failed_ingestion(client)
    families = label_sets(await _metrics(client), OUR_PREFIXES)
    assert {"chat_turns", "http_requests", "card_actions", "kb_ingest"} <= set(families)
    for name, sets in families.items():
        for labels in sets:
            for key, value in labels:
                assert key in ALLOWED_LABELS or key in {"method", "route", "status"}, f"{name} has label {key}"
                if ALLOWED_LABELS.get(key):
                    assert value in ALLOWED_LABELS[key], f"{name}{{{key}={value}}}"
                if key == "route":
                    assert "424242" not in value, f"{name} uses the raw path {value}"
                if key == "status":
                    assert value.isdigit() and len(value) == 3
    routes = {dict(labels).get("route") for labels in families["http_requests"]}
    assert "/me/sessions/{chat_session_id}/messages" in routes


def _seed_slot_and_session(db_engine: Engine) -> tuple[int, int]:
    with db_engine.begin() as conn:
        location = conn.execute(text("SELECT id FROM location LIMIT 1")).scalar_one()
        clinic = conn.execute(text("INSERT INTO clinic (name, location_id) VALUES (:n, :l) RETURNING id"), {"n": f"C{id(conn)}", "l": location}).scalar_one()
        specialty = conn.execute(text("INSERT INTO specialty (name) VALUES (:n) RETURNING id"), {"n": f"S{id(conn)}"}).scalar_one()
        cs = conn.execute(text("INSERT INTO clinic_specialty (clinic_id, specialty_id) VALUES (:c, :s) RETURNING id"), {"c": clinic, "s": specialty}).scalar_one()
        doctor = conn.execute(text("INSERT INTO doctor (name, clinic_specialty_id) VALUES ('Dr', :cs) RETURNING id"), {"cs": cs}).scalar_one()
        slot = conn.execute(text("INSERT INTO slot (doctor_id, start_at, status) VALUES (:d, '2026-12-15 10:00+00', 'available') RETURNING id"), {"d": doctor}).scalar_one()
        profile = conn.execute(text("SELECT p.id FROM profile p JOIN account a ON a.id = p.account_id WHERE a.username = 'mona'")).scalar_one()
        session_id = conn.execute(text("INSERT INTO chat_session (profile_id) VALUES (:p) RETURNING id"), {"p": profile}).scalar_one()
    return slot, session_id


async def _failed_ingestion(client: AsyncClient) -> None:
    from testkit.kb_ingest import scanned_ingest

    app = client.app  # type: ignore[attr-defined]
    runner = app.state.kb_runner
    runner.ingest_function = scanned_ingest
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as admin:
        await admin.post("/auth/login", json={"username": "admin1", "password": "adminpass1"})
        response = await admin.post("/admin/kb-documents", params={"filename": f"scan-{id(admin)}.pdf"}, content=b"%PDF-1.4 scanned")
        assert response.status_code == 201
    await runner.join()


class FixedTimingTurn:
    def __init__(self, agent: str) -> None:
        self.agent = agent

    async def __call__(self, request: TurnRequest) -> AsyncIterator[TurnEvent]:
        for elapsed in (0.0, 0.25, 0.75):
            yield Token(text="x ", elapsed=elapsed)
        yield Done(
            new_rows=[HistoryRow(role="user", content=request.message), HistoryRow(role="assistant", content="x x x")],
            timings=Timings(classify=0.1, rewrite=0.2, embed=0.3, search=0.4, rerank=0.5, ttft=0.6, generate=0.7, total=1.5),
            usage=Usage(prompt_tokens=30, completion_tokens=3),
            agent=self.agent,
        )


@pytest.mark.anyio()
async def test_H2_H3_every_stage_and_agent_is_recorded_from_the_done_timings(client: AsyncClient) -> None:
    app = client.app  # type: ignore[attr-defined]
    before = await _metrics(client)
    for agent in ("knowledge", "scheduling"):
        app.state.turn_runner = FixedTimingTurn(agent)
        app.state.clock.now_value += timedelta(seconds=11)
        assert "event: done" in (await client.post("/me/chat", json={"message": "q"})).text
    after = await _metrics(client)

    def delta(name: str, labels: dict[str, str] | None = None) -> float:
        return metric_value(after, name, labels) - metric_value(before, name, labels)

    assert delta("chat_turns_by_agent_total", {"agent": "knowledge"}) == 1
    assert delta("chat_turns_by_agent_total", {"agent": "scheduling"}) == 1
    for stage, seconds in (("classify", 0.1), ("rewrite", 0.2), ("embed", 0.3), ("search", 0.4), ("rerank", 0.5), ("generate", 0.7)):
        assert delta("chat_stage_duration_seconds_count", {"stage": stage}) == 2, stage
        assert delta("chat_stage_duration_seconds_sum", {"stage": stage}) == pytest.approx(2 * seconds), stage
    assert delta("chat_ttft_seconds_sum") == pytest.approx(1.2)
    assert delta("chat_llm_duration_seconds_sum") == pytest.approx(1.4)
    assert delta("chat_turn_duration_seconds_sum") == pytest.approx(3.0)
    assert delta("chat_chunk_gap_seconds_count") == 4
    assert delta("chat_chunk_gap_seconds_sum") == pytest.approx(2 * 0.75)


@pytest.mark.anyio()
async def test_H3_the_daily_signup_and_login_limits_are_counted(client: AsyncClient) -> None:
    app = client.app  # type: ignore[attr-defined]
    app.state.turn_runner = run_stub_turn
    before = await _metrics(client)
    for i in range(100):
        app.state.clock.now_value += timedelta(seconds=11)
        await client.post("/me/chat", json={"message": f"m{i}"})
    app.state.clock.now_value += timedelta(seconds=11)
    assert (await client.post("/me/chat", json={"message": "over"})).status_code == 429
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as anon:
        statuses: list[int] = []
        while not statuses or statuses[-1] != 429:
            statuses.append((await anon.post("/auth/signup", json={"username": f"u{len(statuses)}x", "password": "password123"})).status_code)
            assert len(statuses) <= 6, "the sign-up limit never triggered"
        for _ in range(11):
            last_login = await anon.post("/auth/login", json={"username": "mona", "password": "wrong-password"})
    assert statuses[-1] == 429 and last_login.status_code == 429
    after = await _metrics(client)
    for limit in ("chat_daily", "signup", "login"):
        assert metric_value(after, "rate_limit_rejections_total", {"limit": limit}) - metric_value(before, "rate_limit_rejections_total", {"limit": limit}) == 1, limit


@pytest.mark.anyio()
async def test_H3_cancel_complaint_and_rejected_card_actions_are_counted(client: AsyncClient, db_engine: Engine) -> None:
    slot, session_id = _seed_slot_and_session(db_engine)
    before = await _metrics(client)
    visit = (await client.post("/me/visits", json={"session_id": session_id, "slot_id": slot})).json()["visit"]["id"]
    assert (await client.post(f"/me/visits/{visit}/cancel", json={"session_id": session_id})).status_code == 200
    assert (await client.post(f"/me/visits/{visit}/cancel", json={"session_id": session_id})).status_code == 409
    with db_engine.begin() as conn:
        conn.execute(text("UPDATE visit SET status = 'completed' WHERE id = :v"), {"v": visit})
    assert (await client.post("/me/complaints", json={"session_id": session_id, "visit_id": visit, "description": "Long wait"})).status_code == 201
    assert (await client.post("/me/visits", json={"session_id": 999999, "slot_id": slot})).status_code == 404
    after = await _metrics(client)
    for action, outcome in (("cancel", "ok"), ("cancel", "conflict"), ("complaint", "ok"), ("book", "rejected")):
        labels = {"action": action, "outcome": outcome}
        assert metric_value(after, "card_actions_total", labels) - metric_value(before, "card_actions_total", labels) == 1, labels


@pytest.mark.anyio()
async def test_H3_a_failed_ingestion_is_counted_and_the_gauge_returns(client: AsyncClient) -> None:
    before = await _metrics(client)
    await _failed_ingestion(client)
    after = await _metrics(client)
    assert metric_value(after, "kb_ingest_total", {"outcome": "failed"}) == metric_value(before, "kb_ingest_total", {"outcome": "failed"}) + 1
    assert metric_value(after, "kb_documents_processing") == metric_value(before, "kb_documents_processing")
