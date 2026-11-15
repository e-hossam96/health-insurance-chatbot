from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chatbot_ai.tools.models import InvalidArgument
from chatbot_ai.tools.ports import ComplaintsPort, SchedulingPort
from testkit.fake_ports import FakeComplaint, fake_ports, sample_catalog

NOW = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
PROFILE_ID = 10
CAIRO = 1


def _ports() -> tuple[SchedulingPort, ComplaintsPort]:
    ports = fake_ports(sample_catalog(), PROFILE_ID, CAIRO, NOW)
    return ports.scheduling, ports.complaints


def test_fake_ports_satisfy_the_protocols() -> None:
    scheduling, complaints = _ports()
    assert isinstance(scheduling, SchedulingPort)
    assert isinstance(complaints, ComplaintsPort)


@pytest.mark.anyio()
async def test_fake_slots_are_open_future_slots_earliest_first() -> None:
    scheduling, _ = _ports()
    assert [c.slot_id for c in await scheduling.available_slots(1, None, None, 3)] == [1]
    assert [c.slot_id for c in await scheduling.available_slots(3, None, None, 3)] == [3]
    card = (await scheduling.available_slots(1, None, None, 3))[0]
    assert card.start_at == "2026-12-15T10:00:00Z"


@pytest.mark.anyio()
async def test_fake_recommendations_prefer_the_profile_location_then_earliest() -> None:
    scheduling, _ = _ports()
    ranked = await scheduling.recommend_doctors(1, None, 3)
    assert [c.doctor_name for c in ranked] == ["Dr. Sara Nabil", "Dr. Lina Fares", "Dr. Omar Hassan"]
    in_giza = await scheduling.recommend_doctors(1, 2, 3)
    assert in_giza[0].doctor_name == "Dr. Omar Hassan"


@pytest.mark.anyio()
async def test_fake_visits_are_bound_to_the_profile() -> None:
    scheduling, _ = _ports()
    assert [v.visit_id for v in await scheduling.my_visits(None)] == [1, 2]
    assert [v.visit_id for v in await scheduling.scheduled_visits(None)] == [1]
    assert await scheduling.scheduled_visits(3) == []


@pytest.mark.anyio()
async def test_fake_complaint_candidates_are_own_completed_visits_without_a_complaint() -> None:
    catalog = sample_catalog()
    complaints = fake_ports(catalog, PROFILE_ID, CAIRO, NOW).complaints
    assert [c.visit_id for c in await complaints.eligible_visits()] == [2]
    catalog.complaints.append(FakeComplaint(1, visit_id=2, description="Long wait", replies=("Sorry",)))
    assert await complaints.eligible_visits() == []
    assert (await complaints.my_complaints())[0].replies == ["Sorry"]


@pytest.mark.anyio()
async def test_fake_catalog_searches_filter_and_validate_ids() -> None:
    scheduling, _ = _ports()
    assert [c.name for c in await scheduling.search_clinics(None, 2)] == ["Cairo Clinic"]
    assert [d.name for d in await scheduling.search_doctors(None, 2, None)] == ["Dr. Omar Hassan"]
    assert [d.name for d in await scheduling.search_doctors(1, None, 2)] == ["Dr. Karim Adel"]
    with pytest.raises(InvalidArgument, match="specialty_id 99"):
        await scheduling.recommend_doctors(99, None, 3)
    with pytest.raises(InvalidArgument, match="location_id 42"):
        await scheduling.search_clinics(42, None)
