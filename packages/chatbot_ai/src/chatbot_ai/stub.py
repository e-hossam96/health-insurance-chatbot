"""Stub agent with scripted scenarios for Phase 5 testing."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from enum import Enum

from chatbot_ai.interface import (
    Cards,
    Done,
    HistoryRow,
    Intent,
    Timings,
    Token,
    TurnEvent,
    TurnRequest,
    Usage,
)


class Scenario(str, Enum):
    text_only = "text_only"
    tool_call_with_cards = "tool_call_with_cards"
    error = "error"
    slow_stream = "slow_stream"


def _classify_scenario(message: str) -> Scenario:
    lower = message.lower()
    if "error" in lower:
        return Scenario.error
    if "slow" in lower:
        return Scenario.slow_stream
    if "book" in lower or "slot" in lower or "cancel" in lower or "complaint" in lower:
        return Scenario.tool_call_with_cards
    return Scenario.text_only


def _classify_intent(message: str) -> str | None:
    lower = message.lower()
    if "book" in lower:
        return "visit.book"
    if "cancel" in lower:
        return "visit.cancel"
    if "complaint" in lower or "file" in lower:
        return "complaint.file"
    if "visit" in lower or "check" in lower:
        return "visit.check"
    if "coverage" in lower or "policy" in lower or "insurance" in lower:
        return "qa.kb"
    return "other"


class StubError(Exception):
    """Raised by the error scenario."""


async def run_stub_turn(
    req: TurnRequest,
    token_delay: float = 0.0,
) -> AsyncIterator[TurnEvent]:
    """Run a scripted stub turn. Yields TurnEvents in the correct order."""
    scenario = _classify_scenario(req.message)
    start = time.monotonic()

    # Intent event (only when needs_label)
    intent_code: str | None = None
    if req.needs_label:
        intent_code = _classify_intent(req.message)
        if intent_code is not None:
            yield Intent(code=intent_code)

    if scenario == Scenario.error:
        raise StubError("Simulated error for testing")

    if scenario == Scenario.text_only:
        reply = f"Hello {req.profile.display_name}, I can help you with that."
        for word in reply.split():
            elapsed = time.monotonic() - start
            yield Token(text=word + " ", elapsed=elapsed)
            if token_delay > 0:
                await asyncio.sleep(token_delay)

        yield Done(
            new_rows=[
                HistoryRow(role="user", content=req.message),
                HistoryRow(role="assistant", content=reply),
            ],
            timings=Timings(total=time.monotonic() - start),
            usage=Usage(prompt_tokens=10, completion_tokens=len(reply.split())),
        )
        return

    if scenario == Scenario.tool_call_with_cards:
        reply = "Here are the available options for you."
        for word in reply.split():
            elapsed = time.monotonic() - start
            yield Token(text=word + " ", elapsed=elapsed)
            if token_delay > 0:
                await asyncio.sleep(token_delay)

        yield Cards(
            type="doctors",
            items=[
                {
                    "slot_id": 1,
                    "doctor_name": "Dr. Sara",
                    "specialty": "Dermatology",
                    "clinic": "Cairo Clinic",
                    "location": "Cairo",
                    "start_at": "2026-12-15T10:00:00Z",
                },
            ],
        )

        tool_call_row = HistoryRow(
            role="assistant",
            content="",
            tool_calls=[{
                "id": "stub_1",
                "type": "function",
                "function": {"name": "get_availability", "arguments": "{}"},
            }],
        )
        tool_result_row = HistoryRow(
            role="tool",
            content='{"slots": []}',
            tool_call_id="stub_1",
            tool_name="get_availability",
        )

        yield Done(
            new_rows=[
                HistoryRow(role="user", content=req.message),
                tool_call_row,
                tool_result_row,
                HistoryRow(role="assistant", content=reply),
            ],
            timings=Timings(
                total=time.monotonic() - start,
                tool_calls=[("get_availability", 0.01)],
            ),
            usage=Usage(prompt_tokens=20, completion_tokens=len(reply.split())),
        )
        return

    if scenario == Scenario.slow_stream:
        reply = "This is a slow response for testing streaming behavior."
        delay = token_delay if token_delay > 0 else 0.05
        for word in reply.split():
            elapsed = time.monotonic() - start
            yield Token(text=word + " ", elapsed=elapsed)
            await asyncio.sleep(delay)

        yield Done(
            new_rows=[
                HistoryRow(role="user", content=req.message),
                HistoryRow(role="assistant", content=reply),
            ],
            timings=Timings(total=time.monotonic() - start),
            usage=Usage(prompt_tokens=10, completion_tokens=len(reply.split())),
        )
