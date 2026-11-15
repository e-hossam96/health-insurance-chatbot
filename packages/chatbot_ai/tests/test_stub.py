"""Contract tests for the stub agent (step 5.1)."""

from __future__ import annotations

import pytest

from chatbot_ai.interface import (
    Cards,
    Done,
    HistoryRow,
    Intent,
    ProfileInfo,
    Token,
    TurnRequest,
)
from chatbot_ai.stub import StubError, run_stub_turn

PROFILE = ProfileInfo(display_name="Sara", location_name="Cairo", location_id=1)


def _req(message: str, needs_label: bool = False) -> TurnRequest:
    return TurnRequest(
        history=[],
        message=message,
        profile=PROFILE,
        needs_label=needs_label,
        session_id=1,
    )


async def _collect(req: TurnRequest) -> list[object]:
    events: list[object] = []
    async for ev in run_stub_turn(req):
        events.append(ev)
    return events


@pytest.mark.anyio()
async def test_text_only_event_order() -> None:
    """Text-only scenario: Token+ then Done with 2 rows."""
    events = await _collect(_req("hello"))
    tokens = [e for e in events if isinstance(e, Token)]
    assert len(tokens) > 0
    done_events = [e for e in events if isinstance(e, Done)]
    assert len(done_events) == 1
    done = done_events[0]
    assert len(done.new_rows) == 2
    assert done.new_rows[0].role == "user"
    assert done.new_rows[1].role == "assistant"
    # Done must be last
    assert isinstance(events[-1], Done)
    # No Cards in text-only
    assert not any(isinstance(e, Cards) for e in events)


@pytest.mark.anyio()
async def test_tool_call_with_cards_event_order() -> None:
    """Tool call scenario: Token+, Cards, then Done with 4 rows (tool call shape)."""
    events = await _collect(_req("I want to book a visit"))
    tokens = [e for e in events if isinstance(e, Token)]
    assert len(tokens) > 0
    cards_events = [e for e in events if isinstance(e, Cards)]
    assert len(cards_events) == 1
    assert cards_events[0].type == "doctors"
    assert len(cards_events[0].items) > 0
    done_events = [e for e in events if isinstance(e, Done)]
    assert len(done_events) == 1
    done = done_events[0]
    # 4 rows: user, assistant (tool_calls), tool, assistant
    assert len(done.new_rows) == 4
    assert done.new_rows[0].role == "user"
    assert done.new_rows[1].role == "assistant"
    assert done.new_rows[1].tool_calls is not None
    assert done.new_rows[2].role == "tool"
    assert done.new_rows[2].tool_call_id is not None
    assert done.new_rows[3].role == "assistant"
    # Cards come after all tokens, before Done
    cards_idx = events.index(cards_events[0])
    last_token_idx = max(i for i, e in enumerate(events) if isinstance(e, Token))
    done_idx = events.index(done)
    assert cards_idx > last_token_idx
    assert cards_idx < done_idx


@pytest.mark.anyio()
async def test_error_scenario_raises() -> None:
    """Error scenario raises StubError."""
    with pytest.raises(StubError, match="Simulated error"):
        async for _ in run_stub_turn(_req("trigger error please")):
            pass


@pytest.mark.anyio()
async def test_slow_stream_event_order() -> None:
    """Slow stream: Token+ then Done, with measurable elapsed times."""
    events = await _collect(_req("slow response", needs_label=False))
    tokens = [e for e in events if isinstance(e, Token)]
    assert len(tokens) > 1
    # Elapsed should be increasing
    for i in range(1, len(tokens)):
        assert tokens[i].elapsed >= tokens[i - 1].elapsed
    assert isinstance(events[-1], Done)


@pytest.mark.anyio()
async def test_intent_emitted_when_needs_label() -> None:
    """Intent event is emitted when needs_label=True."""
    events = await _collect(_req("I want to book a visit", needs_label=True))
    intent_events = [e for e in events if isinstance(e, Intent)]
    assert len(intent_events) == 1
    assert intent_events[0].code == "visit.book"
    # Intent must be first event
    assert isinstance(events[0], Intent)


@pytest.mark.anyio()
async def test_no_intent_when_not_needed() -> None:
    """No Intent event when needs_label=False."""
    events = await _collect(_req("I want to book a visit", needs_label=False))
    assert not any(isinstance(e, Intent) for e in events)


@pytest.mark.anyio()
async def test_intent_before_error() -> None:
    """Error scenario still emits Intent if needs_label before raising."""
    events: list[object] = []
    with pytest.raises(StubError):
        async for ev in run_stub_turn(_req("trigger error", needs_label=True)):
            events.append(ev)
    # Intent should have been yielded before the error
    assert len(events) == 1
    assert isinstance(events[0], Intent)


@pytest.mark.anyio()
async def test_done_has_timings_and_usage() -> None:
    """Done event carries timings and usage."""
    events = await _collect(_req("hello"))
    done = next(e for e in events if isinstance(e, Done))
    assert done.timings.total > 0
    assert done.usage.prompt_tokens > 0
    assert done.usage.completion_tokens > 0


@pytest.mark.anyio()
async def test_tool_call_timings_include_tool_name() -> None:
    """Tool call scenario includes tool call timings."""
    events = await _collect(_req("book a slot"))
    done = next(e for e in events if isinstance(e, Done))
    assert len(done.timings.tool_calls) > 0
    assert done.timings.tool_calls[0][0] == "get_availability"


@pytest.mark.anyio()
async def test_history_row_contract() -> None:
    """HistoryRow has the expected fields."""
    row = HistoryRow(role="user", content="hello")
    assert row.role == "user"
    assert row.content == "hello"
    assert row.tool_calls is None
    assert row.tool_call_id is None
    assert row.tool_name is None

    tool_row = HistoryRow(
        role="tool",
        content="result",
        tool_call_id="call_1",
        tool_name="my_tool",
    )
    assert tool_row.tool_call_id == "call_1"
    assert tool_row.tool_name == "my_tool"
