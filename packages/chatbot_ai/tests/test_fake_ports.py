from __future__ import annotations

from datetime import UTC, datetime

import pytest

from chatbot_ai.interface import ComplaintsPort, SchedulingPort
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
async def test_availability_lists_only_open_future_slots_earliest_first() -> None:
    scheduling, _ = _ports()
    sara = await scheduling.get_availability(doctor_id=1)
    assert [card["slot_id"] for card in sara["cards"]] == [1]
    lina = await scheduling.get_availability(doctor_id=3)
    assert [card["slot_id"] for card in lina["cards"]] == [3]
    assert set(sara["cards"][0]) == {"slot_id", "doctor_name", "specialty", "clinic", "location", "start_at"}
    assert sara["cards"][0]["start_at"] == "2026-12-15T10:00:00Z"


@pytest.mark.anyio()
async def test_recommendations_prefer_the_profile_location_then_earliest() -> None:
    scheduling, _ = _ports()
    ranked = await scheduling.recommend_doctors(specialty_id=1)
    assert [card["doctor_name"] for card in ranked["cards"]] == ["Dr. Sara Nabil", "Dr. Lina Fares", "Dr. Omar Hassan"]
    in_giza = await scheduling.recommend_doctors(specialty_id=1, location_id=2)
    assert in_giza["cards"][0]["doctor_name"] == "Dr. Omar Hassan"


@pytest.mark.anyio()
async def test_visits_and_cancel_proposals_are_bound_to_the_profile() -> None:
    scheduling, _ = _ports()
    assert [v["visit_id"] for v in await scheduling.my_visits()] == [1, 2]
    assert [c["visit_id"] for c in (await scheduling.propose_cancel())["cards"]] == [1]
    assert (await scheduling.propose_cancel(visit_id=3))["cards"] == []


@pytest.mark.anyio()
async def test_complaint_candidates_are_own_completed_visits_without_a_complaint() -> None:
    catalog = sample_catalog()
    complaints = fake_ports(catalog, PROFILE_ID, CAIRO, NOW).complaints
    assert [c["visit_id"] for c in (await complaints.eligible_visits())["cards"]] == [2]
    catalog.complaints.append(FakeComplaint(1, visit_id=2, description="Long wait", replies=("Sorry",)))
    assert (await complaints.eligible_visits())["cards"] == []
    assert (await complaints.my_complaints())[0]["replies"] == ["Sorry"]


@pytest.mark.anyio()
async def test_catalog_searches_filter_by_every_argument() -> None:
    scheduling, _ = _ports()
    assert [c["name"] for c in await scheduling.search_clinics(specialty_id=2)] == ["Cairo Clinic"]
    assert [d["name"] for d in await scheduling.search_doctors(location_id=2)] == ["Dr. Omar Hassan"]
    assert [d["name"] for d in await scheduling.search_doctors(clinic_id=1, specialty_id=2)] == ["Dr. Karim Adel"]
    assert [loc["name"] for loc in await scheduling.list_locations()] == ["Cairo", "Giza"]
