from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from chatbot_ai.clients import RoleClients
from chatbot_ai.interface import Cards, Done, ProfileInfo, Token, TurnRequest
from chatbot_ai.orchestrator import run_turn
from chatbot_ai.settings import AISettings
from testkit.ai_settings import settings_for
from testkit.fake_brain import NO_SLOTS_TEXT, UNKNOWN_SPECIALTY_TEXT
from testkit.fake_openai import FakeOpenAI
from testkit.fake_ports import FakeDoctor, NamedRef, make_fake_ports, sample_catalog

PROFILE = ProfileInfo(display_name="Mona", location_name="Cairo", location_id=1)


@pytest.fixture()
def auto(fake_openai: FakeOpenAI) -> Iterator[AISettings]:
    fake_openai.auto = True
    yield settings_for(fake_openai.base_url)
    fake_openai.auto = False


async def _turn(settings: AISettings, message: str, with_unbooked_specialty: bool = False) -> tuple[str, list[Cards], Done]:
    catalog = sample_catalog()
    if with_unbooked_specialty:
        catalog.specialties.append(NamedRef(id=9, name="Neurology"))
        catalog.doctors.append(FakeDoctor(9, "Dr. No Slots", 1, 9))
    fakes = make_fake_ports(catalog, 10, 1, datetime(2026, 12, 1, tzinfo=UTC))
    clients = RoleClients(settings)
    try:
        request = TurnRequest(history=[], message=message, profile=PROFILE, needs_label=True, session_id=1)
        events = [e async for e in run_turn(request, fakes.as_ports(), settings, clients)]
    finally:
        await clients.aclose()
    done = events[-1]
    assert isinstance(done, Done)
    return "".join(e.text for e in events if isinstance(e, Token)), [e for e in events if isinstance(e, Cards)], done


@pytest.mark.anyio()
async def test_the_brain_books_through_the_real_tool_loop(auto: AISettings) -> None:
    text, cards, done = await _turn(auto, "I need a dermatologist")
    assert [c.type for c in cards] == ["doctors"]
    assert [i["doctor_name"] for i in cards[0].items] == ["Dr. Sara Nabil", "Dr. Lina Fares", "Dr. Omar Hassan"]
    assert "Dr. Sara Nabil at Cairo Clinic on 2026-12-15 10:00 UTC" in text
    assert done.agent == "scheduling"


@pytest.mark.anyio()
async def test_the_brain_reports_no_slots_and_unknown_specialties(auto: AISettings) -> None:
    text, cards, _ = await _turn(auto, "I need a neurologist", with_unbooked_specialty=True)
    assert (text, cards) == (NO_SLOTS_TEXT, [])
    text, cards, _ = await _turn(auto, "I need a dentist")
    assert (text, cards) == (UNKNOWN_SPECIALTY_TEXT, [])
