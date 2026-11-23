from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from itertools import count

import pytest

from chatbot_ai.agents.base import (
    AgentContext,
    AgentEvent,
    AgentNotAvailable,
    AgentResult,
)
from chatbot_ai.clients import RoleClients
from chatbot_ai.intents import AGENT_FOR_INTENT, AgentName, IntentCode, agent_for
from chatbot_ai.interface import (
    Done,
    HistoryRow,
    Intent,
    ProfileInfo,
    Token,
    TurnEvent,
    TurnRequest,
    Usage,
)
from chatbot_ai.languages import LanguageCode
from chatbot_ai.orchestrator import default_agents, run_turn
from chatbot_ai.prompts import agent_system_prompt
from chatbot_ai.settings import AISettings
from testkit.fake_openai import FakeOpenAI, error_reply, json_reply, text_reply
from testkit.fake_ports import fake_ports, sample_catalog

PROFILE = ProfileInfo(display_name="Mona", location_name="Cairo", location_id=1)
PORTS = fake_ports(sample_catalog(), profile_id=10, profile_location_id=1, now=datetime(2026, 12, 1, tzinfo=UTC))


class RecordingAgent:
    def __init__(self, name: AgentName) -> None:
        self.name = name
        self.contexts: list[AgentContext] = []

    async def run(self, context: AgentContext) -> AsyncIterator[AgentEvent]:
        self.contexts.append(context)
        yield Token(text=f"{self.name.value} reply", elapsed=0.0)
        yield AgentResult(rows=[HistoryRow(role="assistant", content=f"{self.name.value} reply")], usage=Usage(5, 2))


def _request(message: str, needs_label: bool = True, history: list[HistoryRow] | None = None) -> TurnRequest:
    return TurnRequest(history=history or [], message=message, profile=PROFILE, needs_label=needs_label, session_id=7)


def _ticks() -> Iterator[float]:
    return (float(i) for i in count())


async def _collect(stream: AsyncIterator[TurnEvent]) -> list[TurnEvent]:
    return [event async for event in stream]


def _recording_registry() -> dict[AgentName, RecordingAgent]:
    return {name: RecordingAgent(name) for name in AgentName}


def test_I2_every_intent_maps_to_its_agent() -> None:
    assert AGENT_FOR_INTENT == {
        IntentCode.visit_book: AgentName.scheduling,
        IntentCode.visit_check: AgentName.scheduling,
        IntentCode.visit_cancel: AgentName.scheduling,
        IntentCode.qa_db: AgentName.scheduling,
        IntentCode.complaint_file: AgentName.complaints,
        IntentCode.complaint_check: AgentName.complaints,
        IntentCode.qa_kb: AgentName.knowledge,
        IntentCode.other: AgentName.responder,
    }
    assert agent_for(None) is AgentName.responder


@pytest.mark.anyio()
@pytest.mark.parametrize("intent", list(IntentCode), ids=[i.value for i in IntentCode])
async def test_I2_I14_scripted_classification_runs_exactly_one_agent(
    intent: IntentCode, fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    fake_openai.queue(json_reply({"intent": intent.value, "language": "en"}), model="router-model")
    registry = _recording_registry()
    events = await _collect(run_turn(_request("msg"), PORTS, ai_settings, role_clients, registry))

    expected = AGENT_FOR_INTENT[intent]
    assert [name for name, agent in registry.items() if agent.contexts] == [expected]
    assert [e.text for e in events if isinstance(e, Token)] == [f"{expected.value} reply"]
    assert len(fake_openai.chat_requests) == 1


@pytest.mark.anyio()
async def test_I3_router_call_is_not_in_the_stored_rows(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    fake_openai.queue(json_reply({"intent": "other", "language": "en"}), model="router-model")
    fake_openai.queue(text_reply("Hello Mona!"), model="chat-model")
    events = await _collect(run_turn(_request("hi"), PORTS, ai_settings, role_clients))

    done = events[-1]
    assert isinstance(done, Done)
    assert done.new_rows == [HistoryRow(role="user", content="hi"), HistoryRow(role="assistant", content="Hello Mona!")]
    assert [r["model"] for r in fake_openai.chat_requests] == ["router-model", "chat-model"]


@pytest.mark.anyio()
async def test_F6_intent_event_comes_first_only_when_a_label_is_needed(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    registry = _recording_registry()
    fake_openai.queue(json_reply({"intent": "qa.kb", "language": "en"}), json_reply({"intent": "visit.book", "language": "en"}), model="router-model")

    labelled = await _collect(run_turn(_request("cover?", needs_label=True), PORTS, ai_settings, role_clients, registry))
    assert labelled[0] == Intent(code="qa.kb")
    assert sum(isinstance(e, Intent) for e in labelled) == 1

    unlabelled = await _collect(run_turn(_request("book", needs_label=False), PORTS, ai_settings, role_clients, registry))
    assert not any(isinstance(e, Intent) for e in unlabelled)
    assert registry[AgentName.scheduling].contexts, "routing still happens when no label is needed"


@pytest.mark.anyio()
async def test_I1_F6_classifier_failure_falls_back_to_the_responder_and_the_next_turn_labels(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    registry = _recording_registry()
    fake_openai.queue(error_reply(500, "router down"), json_reply({"intent": "visit.book", "language": "en"}), model="router-model")

    failed = await _collect(run_turn(_request("book a visit"), PORTS, ai_settings, role_clients, registry))
    assert not any(isinstance(e, Intent) for e in failed)
    assert len(registry[AgentName.responder].contexts) == 1
    assert isinstance(failed[-1], Done)

    recovered = await _collect(run_turn(_request("book a visit"), PORTS, ai_settings, role_clients, registry))
    assert recovered[0] == Intent(code="visit.book")
    assert len(registry[AgentName.scheduling].contexts) == 1


@pytest.mark.anyio()
async def test_I1_router_gets_the_last_6_history_rows(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    history = [HistoryRow(role="user" if i % 2 == 0 else "assistant", content=f"row {i}") for i in range(11)]
    fake_openai.queue(json_reply({"intent": "other", "language": "en"}), model="router-model")
    await _collect(run_turn(_request("yes", history=history), PORTS, ai_settings, role_clients, _recording_registry()))
    router_messages = fake_openai.chat_requests[0]["messages"]
    assert [m["content"] for m in router_messages[1:]] == ["row 6", "row 7", "row 8", "row 9", "row 10", "yes"]


@pytest.mark.anyio()
async def test_unregistered_agent_is_an_error(fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients) -> None:
    fake_openai.queue(json_reply({"intent": "qa.kb", "language": "en"}), model="router-model")
    with pytest.raises(AgentNotAvailable, match="knowledge"):
        await _collect(run_turn(_request("cover?"), PORTS, ai_settings, role_clients, {}))


@pytest.mark.anyio()
async def test_responder_streams_tokens_and_reports_usage_and_timings(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    fake_openai.queue(json_reply({"intent": "other", "language": "en"}), model="router-model")
    fake_openai.queue(text_reply("Hi Mona, how can I help?", prompt_tokens=40, completion_tokens=6), model="chat-model")
    ticks = _ticks()
    events = await _collect(
        run_turn(_request("hello"), PORTS, ai_settings, role_clients, default_agents(), clock=lambda: next(ticks))
    )

    tokens = [e for e in events if isinstance(e, Token)]
    assert "".join(t.text for t in tokens) == "Hi Mona, how can I help?"
    assert [t.elapsed for t in tokens] == sorted(t.elapsed for t in tokens)
    done = events[-1]
    assert isinstance(done, Done)
    router_usage = Usage(prompt_tokens=10, completion_tokens=4)
    assert done.usage == Usage(prompt_tokens=40 + router_usage.prompt_tokens, completion_tokens=6 + router_usage.completion_tokens)
    assert done.timings.classify == 1.0
    assert done.timings.ttft > 0
    assert done.timings.total > done.timings.generate > 0

    chat_request = fake_openai.chat_requests[1]
    assert chat_request["stream"] is True
    assert chat_request["stream_options"] == {"include_usage": True}
    assert chat_request["max_completion_tokens"] == ai_settings.ai_chat_max_output_tokens == 800
    assert "tools" not in chat_request


@pytest.mark.anyio()
async def test_I4_agents_get_the_shared_prompt_blocks_and_the_full_history(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    history = [
        HistoryRow(role="user", content="book derm"),
        HistoryRow(
            role="assistant",
            content="",
            tool_calls=[{"id": "c1", "type": "function", "function": {"name": "get_availability", "arguments": "{}"}}],
        ),
        HistoryRow(role="tool", content='{"slots": []}', tool_call_id="c1", tool_name="get_availability"),
        HistoryRow(role="assistant", content="No slots."),
    ]
    fake_openai.queue(json_reply({"intent": "other", "language": "en"}), model="router-model")
    fake_openai.queue(text_reply("ok"), model="chat-model")
    await _collect(run_turn(_request("thanks", history=history), PORTS, ai_settings, role_clients))

    messages = fake_openai.chat_requests[1]["messages"]
    system = messages[0]["content"]
    assert system == agent_system_prompt(AgentName.responder, PROFILE, LanguageCode.english)
    for phrase in ("American English", "UTC", "medical advice", "fetch them again", "tools you do not have", "Mona", "location id 1"):
        assert phrase in system
    assert [m["role"] for m in messages[1:]] == ["user", "assistant", "tool", "assistant", "user"]
    assert messages[2]["tool_calls"][0]["id"] == "c1"
    assert messages[-1] == {"role": "user", "content": "thanks"}
