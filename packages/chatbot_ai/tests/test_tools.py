from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime

import pytest

from chatbot_ai.tools.ports import ComplaintsPort, SchedulingPort
from chatbot_ai.tools.registry import COMPLAINT_TOOLS, SCHEDULING_TOOLS, Tool
from testkit.fake_ports import FakePorts, make_fake_ports, sample_catalog

NOW = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
ALL_TOOLS: tuple[Tool, ...] = SCHEDULING_TOOLS + COMPLAINT_TOOLS
DOCTOR_CARD_FIELDS = {"slot_id", "doctor_name", "specialty", "clinic", "location", "start_at"}
VISIT_CARD_FIELDS = {"visit_id", "start_at", "doctor_name", "specialty", "clinic"}
READ_ONLY_PORT_METHODS = {
    "list_locations",
    "list_specialties",
    "search_clinics",
    "search_doctors",
    "available_slots",
    "recommend_doctors",
    "my_visits",
    "scheduled_visits",
    "my_complaints",
    "eligible_visits",
}


def _fakes() -> FakePorts:
    return make_fake_ports(sample_catalog(), profile_id=10, profile_location_id=1, now=NOW)


def _tool(name: str) -> Tool:
    return next(t for t in ALL_TOOLS if t.name == name)


def _parameters(tool: Tool) -> dict[str, object]:
    params: dict[str, object] = tool.definition()["function"]["parameters"]
    return params


def test_D9_the_tool_registry_has_no_write_tool() -> None:
    assert {t.kind for t in ALL_TOOLS} <= {"read", "propose"}
    port_methods = {
        name
        for port in (SchedulingPort, ComplaintsPort)
        for name, _ in inspect.getmembers(port, inspect.isfunction)
        if not name.startswith("_")
    }
    assert port_methods == READ_ONLY_PORT_METHODS
    assert [t.name for t in SCHEDULING_TOOLS] == [
        "list_locations",
        "list_specialties",
        "search_clinics",
        "search_doctors",
        "get_availability",
        "recommend_doctors",
        "my_visits",
        "propose_cancel",
    ]
    assert [t.name for t in COMPLAINT_TOOLS] == ["my_complaints", "eligible_visits"]


def test_B6_I4_no_tool_takes_a_profile_or_account_id() -> None:
    for tool in ALL_TOOLS:
        properties = _parameters(tool).get("properties", {})
        assert isinstance(properties, dict)
        assert not any("profile" in key or "account" in key or key == "user_id" for key in properties), tool.name
        assert _parameters(tool).get("additionalProperties") is False, tool.name


@pytest.mark.anyio()
async def test_B6_a_model_supplied_profile_id_is_rejected_before_the_port_is_called() -> None:
    fakes = _fakes()
    outcome = await _tool("my_visits").invoke(fakes.as_ports(), json.dumps({"profile_id": 11}))
    assert "error" in json.loads(outcome.content)
    assert "profile_id" in outcome.content
    assert fakes.scheduling.calls == []
    outcome = await _tool("propose_cancel").invoke(fakes.as_ports(), json.dumps({"visit_id": 3, "profile_id": 11}))
    assert outcome.cards is None
    assert fakes.scheduling.calls == []


@pytest.mark.anyio()
async def test_B6_visits_and_cancel_cards_only_cover_the_acting_profile() -> None:
    fakes = _fakes()
    visits = json.loads((await _tool("my_visits").invoke(fakes.as_ports(), "{}")).content)["visits"]
    assert [v["visit_id"] for v in visits] == [1, 2]
    other_users_visit = await _tool("propose_cancel").invoke(fakes.as_ports(), json.dumps({"visit_id": 3}))
    assert other_users_visit.cards is None


def test_I5_tools_take_typed_ids_and_no_free_text_query() -> None:
    for tool in ALL_TOOLS:
        properties = _parameters(tool).get("properties", {})
        assert isinstance(properties, dict)
        for name in properties:
            assert name.endswith("_id") or name in {"from_date", "to_date", "status"}, f"{tool.name}.{name}"


@pytest.mark.anyio()
async def test_I5_unknown_catalog_ids_are_reported_to_the_model() -> None:
    fakes = _fakes()
    outcome = await _tool("recommend_doctors").invoke(fakes.as_ports(), json.dumps({"specialty_id": 99}))
    assert json.loads(outcome.content) == {"error": "unknown specialty_id 99"}
    assert outcome.cards is None
    bad_type = await _tool("get_availability").invoke(fakes.as_ports(), json.dumps({"doctor_id": "Dr. Sara"}))
    assert "invalid arguments for get_availability" in bad_type.content


@pytest.mark.anyio()
async def test_C7_D5_doctor_cards_match_api_md_and_keep_the_ranked_order() -> None:
    fakes = _fakes()
    outcome = await _tool("recommend_doctors").invoke(fakes.as_ports(), json.dumps({"specialty_id": 1}))
    assert outcome.cards is not None
    assert outcome.cards.type == "doctors"
    assert [item["doctor_name"] for item in outcome.cards.items] == ["Dr. Sara Nabil", "Dr. Lina Fares", "Dr. Omar Hassan"]
    assert all(set(item) == DOCTOR_CARD_FIELDS for item in outcome.cards.items)
    content = json.loads(outcome.content)
    assert [c["doctor_name"] for c in content["shown_as_cards"]] == [i["doctor_name"] for i in outcome.cards.items]
    assert "Keep this order" in content["note"]


@pytest.mark.anyio()
async def test_C7_availability_offers_at_most_three_cards_and_ten_times() -> None:
    catalog = sample_catalog()
    from testkit.fake_ports import FakeSlot

    for index in range(12):
        catalog.slots.append(FakeSlot(100 + index, 4, datetime(2026, 12, 2 + index, 9, tzinfo=UTC)))
    fakes = make_fake_ports(catalog, 10, 1, NOW)
    outcome = await _tool("get_availability").invoke(fakes.as_ports(), json.dumps({"doctor_id": 4}))
    assert outcome.cards is not None
    assert [item["slot_id"] for item in outcome.cards.items] == [100, 101, 102]
    assert len(json.loads(outcome.content)["more_slot_times"]) == 10
    empty = await _tool("get_availability").invoke(fakes.as_ports(), json.dumps({"doctor_id": 4, "from_date": "2027-01-01"}))
    assert empty.cards is None


@pytest.mark.anyio()
async def test_D8_E1_E2_visit_cards_match_api_md() -> None:
    fakes = _fakes()
    cancel = await _tool("propose_cancel").invoke(fakes.as_ports(), "{}")
    assert cancel.cards is not None and cancel.cards.type == "cancel_confirm"
    assert [i["visit_id"] for i in cancel.cards.items] == [1]
    complaint = await _tool("eligible_visits").invoke(fakes.as_ports(), "{}")
    assert complaint.cards is not None and complaint.cards.type == "visits_for_complaint"
    assert [i["visit_id"] for i in complaint.cards.items] == [2]
    for item in (*cancel.cards.items, *complaint.cards.items):
        assert set(item) == VISIT_CARD_FIELDS


@pytest.mark.anyio()
async def test_F9_propose_results_tell_the_model_to_name_the_options() -> None:
    fakes = _fakes()
    for name, args in (("recommend_doctors", {"specialty_id": 1}), ("propose_cancel", {}), ("eligible_visits", {})):
        outcome = await _tool(name).invoke(fakes.as_ports(), json.dumps(args))
        assert "Name each option in your reply" in json.loads(outcome.content)["note"], name
