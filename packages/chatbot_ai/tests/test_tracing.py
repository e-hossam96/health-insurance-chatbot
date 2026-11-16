from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from chatbot_ai.clients import RoleClients
from chatbot_ai.ingest import delete_document, ingest
from chatbot_ai.interface import Done, ProfileInfo, TurnRequest
from chatbot_ai.orchestrator import run_turn
from chatbot_ai.settings import AISettings
from chatbot_ai.tracing import (
    LangfuseTracer,
    NoopTracer,
    langfuse_session_id,
    make_tracer,
)
from testkit.ai_settings import settings_for
from testkit.fake_openai import (
    FakeOpenAI,
    ToolCallSpec,
    json_reply,
    text_reply,
    tool_reply,
)
from testkit.fake_ports import make_fake_ports, sample_catalog

PROFILE = ProfileInfo(display_name="Mona", location_name="Cairo", location_id=1)


@pytest.fixture()
def exporter() -> Iterator[InMemorySpanExporter]:
    yield InMemorySpanExporter()


@pytest.fixture()
def langfuse_client(exporter: InMemorySpanExporter) -> Iterator[Langfuse]:
    client = Langfuse(public_key=f"pk-{uuid.uuid4().hex}", secret_key="sk-test", host="http://127.0.0.1:9", span_exporter=exporter, flush_at=1)
    yield client
    client.shutdown()


def _attributes(span: ReadableSpan) -> dict[str, object]:
    return dict(span.attributes or {})


def _session_ids(spans: list[ReadableSpan]) -> set[object]:
    return {value for span in spans for key, value in _attributes(span).items() if "session" in key}


async def _run(settings: AISettings, tracer: LangfuseTracer, message: str, session_id: int, ready: list[int] | None = None) -> Done:
    fakes = make_fake_ports(sample_catalog(), 10, 1, datetime(2026, 12, 1, tzinfo=UTC))
    fakes.knowledge.ready_ids.extend(ready or [])
    clients = RoleClients(settings, _tracer=tracer)
    try:
        request = TurnRequest(history=[], message=message, profile=PROFILE, needs_label=False, session_id=session_id)
        events = [e async for e in run_turn(request, fakes.as_ports(), settings, clients)]
    finally:
        await clients.aclose()
    done = events[-1]
    assert isinstance(done, Done)
    return done


def test_F7_the_langfuse_session_id_is_chat_dash_the_session_id() -> None:
    assert langfuse_session_id(42) == "chat-42"


def test_F7_tracing_is_off_without_keys() -> None:
    assert isinstance(make_tracer(None, None, None), NoopTracer)
    assert isinstance(make_tracer("pk", None, "http://x"), NoopTracer)
    assert isinstance(make_tracer(None, "sk", "http://x"), NoopTracer)
    assert isinstance(RoleClients(settings_for("http://x/v1")).tracer(), NoopTracer)


def test_F7_the_tracer_is_built_from_the_langfuse_settings() -> None:
    settings = settings_for("http://x/v1", langfuse_public_key=f"pk-{uuid.uuid4().hex}", langfuse_secret_key="sk", langfuse_host="http://127.0.0.1:9")
    clients = RoleClients(settings)
    assert isinstance(clients.tracer(), LangfuseTracer)
    assert clients.tracer() is clients.tracer()


@pytest.mark.anyio()
async def test_F7_a_turn_without_keys_creates_no_spans(fake_openai: FakeOpenAI, exporter: InMemorySpanExporter) -> None:
    settings = settings_for(fake_openai.base_url)
    fake_openai.queue(json_reply({"intent": "other"}), model="router-model")
    fake_openai.queue(text_reply("hi"), model="chat-model")
    fakes = make_fake_ports(sample_catalog(), 10, 1, datetime(2026, 12, 1, tzinfo=UTC))
    clients = RoleClients(settings)
    try:
        request = TurnRequest(history=[], message="hi", profile=PROFILE, needs_label=False, session_id=1)
        [e async for e in run_turn(request, fakes.as_ports(), settings, clients)]
        assert isinstance(clients.tracer(), NoopTracer)
    finally:
        await clients.aclose()
    assert list(exporter.get_finished_spans()) == []


@pytest.mark.anyio()
async def test_F7_a_tool_turn_is_one_trace_with_spans_for_classify_generate_and_each_tool(
    fake_openai: FakeOpenAI, langfuse_client: Langfuse, exporter: InMemorySpanExporter
) -> None:
    settings = settings_for(fake_openai.base_url)
    fake_openai.queue(json_reply({"intent": "visit.book"}), model="router-model")
    fake_openai.queue(
        tool_reply(ToolCallSpec("list_specialties", {})),
        tool_reply(ToolCallSpec("recommend_doctors", {"specialty_id": 1})),
        text_reply("Dr. Sara Nabil is first."),
        model="chat-model",
    )
    await _run(settings, LangfuseTracer(langfuse_client), "I need a dermatologist", 7)
    langfuse_client.flush()
    spans = list(exporter.get_finished_spans())

    names = [span.name for span in spans]
    assert names.count("chat turn") == 1
    assert names.count("classify") == 1
    assert names.count("generate") == 3
    assert {"list_specialties", "recommend_doctors"} <= set(names)
    assert len({span.context.trace_id for span in spans if span.context}) == 1
    assert _session_ids(spans) == {"chat-7"}
    root = next(span for span in spans if span.name == "chat turn")
    children = [span for span in spans if span.parent and root.context and span.parent.span_id == root.context.span_id]
    assert {span.name for span in children} >= {"classify", "generate", "recommend_doctors"}


@pytest.mark.anyio()
async def test_F7_a_knowledge_turn_has_spans_for_every_pipeline_stage(
    fake_openai: FakeOpenAI, langfuse_client: Langfuse, exporter: InMemorySpanExporter, tmp_path: Path
) -> None:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=f"trace-{uuid.uuid4().hex[:10]}")
    source = tmp_path / "policy.txt"
    source.write_text("Outpatient visits have a co-pay of 50 EGP.", encoding="utf-8")
    await asyncio.to_thread(ingest, 31, str(source), "txt", settings)
    try:
        fake_openai.queue(json_reply({"intent": "qa.kb"}), model="router-model")
        fake_openai.queue(json_reply({"standalone": "What is the outpatient co-pay?", "alternates": ["co-pay", "visit cost"]}), model="rewrite-model")
        fake_openai.queue(text_reply("50 EGP."), model="chat-model")
        await _run(settings, LangfuseTracer(langfuse_client), "co-pay?", 8, ready=[31])
        langfuse_client.flush()
    finally:
        await asyncio.to_thread(delete_document, 31, settings)
    spans = list(exporter.get_finished_spans())
    names = {span.name for span in spans}
    assert {"chat turn", "classify", "rewrite", "embed", "search", "rerank", "generate"} <= names
    assert _session_ids(spans) == {"chat-8"}
    assert len({span.context.trace_id for span in spans if span.context}) == 1
    root = next(span for span in spans if span.name == "chat turn")
    assert root.context is not None
    stage_spans = [span for span in spans if span.name in {"classify", "rewrite", "embed", "search", "rerank", "generate"}]
    assert all(span.parent is not None and span.parent.trace_id == root.context.trace_id for span in stage_spans)
