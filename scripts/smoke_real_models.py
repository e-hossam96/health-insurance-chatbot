from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from chatbot_ai.clients import RoleClients
from chatbot_ai.evals.routing import load_routing, run_routing
from chatbot_ai.ingest import delete_document, ingest
from chatbot_ai.interface import (
    Cards,
    Done,
    Intent,
    ProfileInfo,
    Token,
    TurnEvent,
    TurnRequest,
)
from chatbot_ai.orchestrator import run_turn
from chatbot_ai.settings import AISettings, Role
from testkit.fake_ports import FakePorts, make_fake_ports, sample_catalog

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "packages" / "chatbot_ai" / "src" / "chatbot_ai" / "evals"
SCRATCH_DOCUMENT = 990001
PROFILE = ProfileInfo(display_name="Mona", location_name="Cairo", location_id=1)


def _ports(ready: list[int]) -> FakePorts:
    fakes = make_fake_ports(sample_catalog(), 10, 1, datetime(2026, 12, 1, tzinfo=UTC))
    fakes.knowledge.ready_ids.extend(ready)
    return fakes


async def _turn(settings: AISettings, clients: RoleClients, fakes: FakePorts, message: str) -> list[TurnEvent]:
    request = TurnRequest(history=[], message=message, profile=PROFILE, needs_label=True, session_id=0)
    return [event async for event in run_turn(request, fakes.as_ports(), settings, clients)]


def _summary(name: str, events: list[TurnEvent]) -> tuple[str, Done]:
    text = "".join(e.text for e in events if isinstance(e, Token))
    intents = [e.code for e in events if isinstance(e, Intent)]
    cards = [(e.type, len(e.items)) for e in events if isinstance(e, Cards)]
    done = events[-1]
    assert isinstance(done, Done)
    tools = [call["function"]["name"] for row in done.new_rows for call in row.tool_calls or []]
    timings = done.timings
    print(f"\n== {name}\nintent: {intents}\ntools: {tools}\ncards: {cards}\nusage: {done.usage}")
    print(f"timings: classify={timings.classify:.2f}s rewrite={timings.rewrite:.2f}s search={timings.search:.2f}s ttft={timings.ttft:.2f}s total={timings.total:.2f}s")
    print(f"reply: {text}")
    return text, done


async def main() -> int:
    settings = AISettings()  # type: ignore[call-arg]  # values come from .env
    for role in (Role.chat, Role.router, Role.rewrite, Role.embedding):
        print(f"{role.value}: {settings.role(role).model}")
    problems: list[str] = []
    clients = RoleClients(settings)
    try:
        routing = await run_routing(load_routing(EVALS / "datasets" / "routing.jsonl")[:6], clients.get(Role.router), settings.ai_router_history_rows)
        print(f"\n== routing (6 starter cards): accuracy {routing.accuracy:.2f}, mistakes {[m.id for m in routing.mistakes]}")
        if routing.accuracy < 0.8:
            problems.append("routing accuracy below 0.8 on the starter cards")

        result = await asyncio.to_thread(ingest, SCRATCH_DOCUMENT, str(EVALS / "kb_fixtures" / "member_guide.docx"), "docx", settings)
        print(f"\n== ingest: {result.chunk_count} chunks, {result.table_chunks} tables, embed {result.timings.embed:.2f}s")

        text, done = _summary("knowledge", await _turn(settings, clients, _ports([SCRATCH_DOCUMENT]), "Does an MRI scan need approval, and how far ahead?"))
        if "3 working days" not in text:
            problems.append("the knowledge answer did not give the MRI lead time")
        if "search_kb" not in [c["function"]["name"] for r in done.new_rows for c in r.tool_calls or []]:
            problems.append("the knowledge turn did not record search_kb")

        fakes = _ports([])
        text, done = _summary("booking", await _turn(settings, clients, fakes, "I need a dermatologist"))
        if "recommend_doctors" not in fakes.scheduling.calls and "available_slots" not in fakes.scheduling.calls:
            problems.append("the booking turn offered no slots")
        if "Sara" not in text and "Lina" not in text and "Omar" not in text:
            problems.append("the booking reply does not name the offered doctors (F9)")
    finally:
        await clients.aclose()
        await asyncio.to_thread(delete_document, SCRATCH_DOCUMENT, settings)

    print("\nproblems:", problems or "none")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
