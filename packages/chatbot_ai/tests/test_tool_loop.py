from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from chatbot_ai.clients import RoleClients
from chatbot_ai.intents import AgentName
from chatbot_ai.interface import (
    Cards,
    Done,
    HistoryRow,
    ProfileInfo,
    TurnEvent,
    TurnRequest,
)
from chatbot_ai.languages import LanguageCode
from chatbot_ai.orchestrator import run_turn
from chatbot_ai.prompts import agent_system_prompt
from chatbot_ai.settings import AISettings
from testkit.ai_settings import settings_for
from testkit.fake_openai import (
    FakeOpenAI,
    ToolCallSpec,
    json_reply,
    text_reply,
    tool_reply,
)
from testkit.fake_ports import FakePorts, make_fake_ports, sample_catalog

PROFILE = ProfileInfo(display_name="Mona", location_name="Cairo", location_id=1)
NOW = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
SCHEDULING_TOOL_NAMES = {
    "list_locations",
    "list_specialties",
    "search_clinics",
    "search_doctors",
    "get_availability",
    "recommend_doctors",
    "my_visits",
    "propose_cancel",
}
COMPLAINT_TOOL_NAMES = {"my_complaints", "eligible_visits"}


def _request(message: str, history: list[HistoryRow] | None = None) -> TurnRequest:
    return TurnRequest(history=history or [], message=message, profile=PROFILE, needs_label=False, session_id=3)


def _fakes() -> FakePorts:
    return make_fake_ports(sample_catalog(), profile_id=10, profile_location_id=1, now=NOW)


async def _collect(stream: AsyncIterator[TurnEvent]) -> list[TurnEvent]:
    return [event async for event in stream]


def _offered_tools(request: dict[str, object]) -> set[str]:
    tools = request.get("tools") or []
    assert isinstance(tools, list)
    return {tool["function"]["name"] for tool in tools}


@pytest.mark.anyio()
async def test_scheduling_turn_runs_tools_and_emits_cards_after_the_last_token(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    fakes = _fakes()
    fake_openai.queue(json_reply({"intent": "visit.book", "language": "en"}), model="router-model")
    fake_openai.queue(
        tool_reply(ToolCallSpec("list_specialties", {}, id="c1")),
        tool_reply(ToolCallSpec("recommend_doctors", {"specialty_id": 1}, id="c2")),
        text_reply("Dr. Sara Nabil at Cairo Clinic on Tue 15 Dec, 10:00 UTC is the earliest."),
        model="chat-model",
    )
    events = await _collect(run_turn(_request("I need a dermatologist"), fakes.as_ports(), ai_settings, role_clients))

    kinds = [type(e).__name__ for e in events]
    assert kinds[-2:] == ["Cards", "Done"]
    assert kinds.index("Cards") > max(i for i, k in enumerate(kinds) if k == "Token")
    cards = events[-2]
    assert isinstance(cards, Cards) and cards.type == "doctors" and len(cards.items) == 3

    done = events[-1]
    assert isinstance(done, Done)
    assert [(r.role, r.tool_name) for r in done.new_rows] == [
        ("user", None),
        ("assistant", None),
        ("tool", "list_specialties"),
        ("assistant", None),
        ("tool", "recommend_doctors"),
        ("assistant", None),
    ]
    assert done.new_rows[1].tool_calls == [
        {"id": "c1", "type": "function", "function": {"name": "list_specialties", "arguments": "{}"}}
    ]
    assert done.new_rows[2].tool_call_id == "c1"
    assert json.loads(done.new_rows[4].content)["shown_as_cards"][0]["doctor_name"] == "Dr. Sara Nabil"
    assert [name for name, _ in done.timings.tool_calls] == ["list_specialties", "recommend_doctors"]
    assert fakes.scheduling.calls == ["list_specialties", "recommend_doctors"]

    chat_requests = fake_openai.chat_requests[1:]
    assert all(_offered_tools(r) == SCHEDULING_TOOL_NAMES for r in chat_requests)
    assert chat_requests[2]["messages"][-1]["role"] == "tool"
    assert chat_requests[2]["messages"][-1]["tool_call_id"] == "c2"


@pytest.mark.anyio()
async def test_the_tool_loop_stops_at_the_round_limit(fake_openai: FakeOpenAI) -> None:
    settings = settings_for(fake_openai.base_url, ai_max_tool_rounds=2)
    clients = RoleClients(settings)
    fake_openai.queue(json_reply({"intent": "visit.check", "language": "en"}), model="router-model")
    fake_openai.queue(
        tool_reply(ToolCallSpec("my_visits", {})),
        tool_reply(ToolCallSpec("my_visits", {})),
        text_reply("You have two visits."),
        model="chat-model",
    )
    try:
        events = await _collect(run_turn(_request("my visits"), _fakes().as_ports(), settings, clients))
    finally:
        await clients.aclose()

    chat_requests = fake_openai.chat_requests[1:]
    assert len(chat_requests) == 3
    assert [bool(_offered_tools(r)) for r in chat_requests] == [True, True, False]
    done = events[-1]
    assert isinstance(done, Done)
    assert done.new_rows[-1] == HistoryRow(role="assistant", content="You have two visits.")
    assert fake_openai.pending() == 0


@pytest.mark.anyio()
async def test_a_tool_call_offered_in_the_final_round_is_not_executed(fake_openai: FakeOpenAI) -> None:
    settings = settings_for(fake_openai.base_url, ai_max_tool_rounds=1)
    clients = RoleClients(settings)
    fakes = _fakes()
    fake_openai.queue(json_reply({"intent": "visit.check", "language": "en"}), model="router-model")
    fake_openai.queue(
        tool_reply(ToolCallSpec("my_visits", {})),
        tool_reply(ToolCallSpec("my_visits", {}), content="Here they are."),
        model="chat-model",
    )
    try:
        events = await _collect(run_turn(_request("my visits"), fakes.as_ports(), settings, clients))
    finally:
        await clients.aclose()
    assert fakes.scheduling.calls == ["my_visits"]
    done = events[-1]
    assert isinstance(done, Done)
    assert done.new_rows[-1] == HistoryRow(role="assistant", content="Here they are.")


def test_F5_F8_F9_I4_prompt_blocks_for_the_tool_agents() -> None:
    scheduling = agent_system_prompt(AgentName.scheduling, PROFILE, LanguageCode.english)
    complaints = agent_system_prompt(AgentName.complaints, PROFILE, LanguageCode.english)
    for prompt in (scheduling, complaints):
        assert "fetch them again with a tool" in prompt
        assert "Never give medical advice" in prompt
        assert "help them file a complaint" in prompt
        assert "tool calls from tools you do not have now" in prompt
        assert "You never create, change or cancel anything yourself" in prompt
        assert "American English" in prompt and "UTC" in prompt
        assert "The cards are not saved" in prompt
    assert "name each one in your reply" in scheduling
    assert "already ranked" in scheduling


@pytest.mark.anyio()
async def test_I4_I14_cross_agent_turns_only_offer_and_run_the_current_agents_tools(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    fakes = _fakes()
    history: list[HistoryRow] = []

    fake_openai.queue(json_reply({"intent": "visit.book", "language": "en"}), model="router-model")
    fake_openai.queue(tool_reply(ToolCallSpec("recommend_doctors", {"specialty_id": 1}, id="s1")), text_reply("Dr. Sara Nabil is first."), model="chat-model")
    first = await _collect(run_turn(_request("derm please", history), fakes.as_ports(), ai_settings, role_clients))
    first_done = first[-1]
    assert isinstance(first_done, Done)
    history += first_done.new_rows

    fake_openai.queue(json_reply({"intent": "complaint.file", "language": "en"}), model="router-model")
    fake_openai.queue(
        tool_reply(ToolCallSpec("recommend_doctors", {"specialty_id": 1}, id="x1")),
        tool_reply(ToolCallSpec("eligible_visits", {}, id="x2")),
        text_reply("Pick the visit with Dr. Sara Nabil on Mon 2 Nov, 10:00 UTC."),
        model="chat-model",
    )
    second = await _collect(run_turn(_request("I want to complain", history), fakes.as_ports(), ai_settings, role_clients))
    second_done = second[-1]
    assert isinstance(second_done, Done)
    foreign_result = next(r for r in second_done.new_rows if r.tool_call_id == "x1")
    assert "not available here" in json.loads(foreign_result.content)["error"]
    second_cards = [e for e in second if isinstance(e, Cards)]
    assert [c.type for c in second_cards] == ["visits_for_complaint"]
    history += second_done.new_rows

    fake_openai.queue(json_reply({"intent": "visit.book", "language": "en"}), model="router-model")
    fake_openai.queue(tool_reply(ToolCallSpec("eligible_visits", {}, id="y1")), text_reply("Let me look again."), model="chat-model")
    third = await _collect(run_turn(_request("back to booking", history), fakes.as_ports(), ai_settings, role_clients))
    third_done = third[-1]
    assert isinstance(third_done, Done)
    assert "not available here" in next(r for r in third_done.new_rows if r.tool_call_id == "y1").content

    assert fakes.scheduling.calls == ["recommend_doctors"]
    assert fakes.complaints.calls == ["eligible_visits"]
    offered = [_offered_tools(r) for r in fake_openai.chat_requests if r["model"] == "chat-model" and r.get("tools")]
    assert offered == [SCHEDULING_TOOL_NAMES] * 2 + [COMPLAINT_TOOL_NAMES] * 3 + [SCHEDULING_TOOL_NAMES] * 2
    third_request_messages = fake_openai.chat_requests[-2]["messages"]
    assert any(m.get("tool_calls") for m in third_request_messages), "the history keeps earlier agents' tool calls (I4)"
    third_tool_names = [call["function"]["name"] for row in third_done.new_rows for call in row.tool_calls or []]
    assert third_tool_names == ["eligible_visits"], "the third turn re-fetches through its own tools instead of reusing old results"
