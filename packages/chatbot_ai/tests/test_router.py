from __future__ import annotations

import pytest

from chatbot_ai.clients import RoleClients
from chatbot_ai.intents import IntentCode
from chatbot_ai.interface import HistoryRow
from chatbot_ai.router import classify, router_messages, router_window
from chatbot_ai.settings import Role
from testkit.fake_openai import (
    ChatReply,
    FakeOpenAI,
    error_reply,
    json_reply,
    text_reply,
)

F6_CODES = ["visit.book", "visit.check", "visit.cancel", "complaint.file", "complaint.check", "qa.db", "qa.kb", "other"]
TOOL_CALL = [{"id": "c1", "type": "function", "function": {"name": "get_availability", "arguments": "{}"}}]


def _rows(count: int) -> list[HistoryRow]:
    return [HistoryRow(role="user" if i % 2 == 0 else "assistant", content=f"row {i}") for i in range(count)]


def test_I1_window_is_the_last_6_rows_starting_at_a_user_row() -> None:
    rows = _rows(10)
    window = router_window(rows, 6)
    assert [r.content for r in window] == ["row 4", "row 5", "row 6", "row 7", "row 8", "row 9"]
    shifted = router_window(_rows(11), 6)
    assert shifted[0].role == "user"
    assert [r.content for r in shifted] == ["row 6", "row 7", "row 8", "row 9", "row 10"]
    assert router_window([HistoryRow(role="assistant", content="only")], 6) == []


def test_I1_router_sees_the_conversation_text_but_not_tool_rows() -> None:
    history = [
        HistoryRow(role="user", content="I need a dermatologist"),
        HistoryRow(role="assistant", content="", tool_calls=TOOL_CALL),
        HistoryRow(role="tool", content='{"slots": []}', tool_call_id="c1"),
        HistoryRow(role="assistant", content="Dr. Sara or Dr. Lina?"),
    ]
    messages = router_messages(history, "the second one", 6)
    assert messages[0]["role"] == "system"
    assert [(m["role"], m.get("content")) for m in messages[1:]] == [
        ("user", "I need a dermatologist"),
        ("assistant", "Dr. Sara or Dr. Lina?"),
        ("user", "the second one"),
    ]


@pytest.mark.anyio()
async def test_I1_classifier_uses_structured_output_with_the_F6_enum(
    fake_openai: FakeOpenAI, role_clients: RoleClients
) -> None:
    fake_openai.queue(json_reply({"intent": "qa.kb", "language": "en"}), model="router-model")
    result = await classify(role_clients.get(Role.router), [], "Is maternity covered?", 6)
    assert result.intent is IntentCode.qa_kb
    request = fake_openai.chat_requests[0]
    assert request["model"] == "router-model"
    schema = request["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["properties"]["intent"]["enum"] == F6_CODES
    assert request["messages"][-1] == {"role": "user", "content": "Is maternity covered?"}
    assert result.usage.prompt_tokens == 10


@pytest.mark.anyio()
@pytest.mark.parametrize(
    "reply",
    [error_reply(500, "router down"), error_reply(429, "rate limited"), text_reply("not json at all")],
    ids=["server-error", "rate-limited", "unparseable"],
)
async def test_I1_classifier_failure_returns_no_intent(
    fake_openai: FakeOpenAI, role_clients: RoleClients, reply: ChatReply
) -> None:
    fake_openai.queue(reply, model="router-model")
    result = await classify(role_clients.get(Role.router), [], "hello", 6)
    assert result.intent is None
