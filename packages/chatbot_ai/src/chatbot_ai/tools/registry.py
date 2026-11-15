from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

from openai.types.chat import ChatCompletionToolParam
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from chatbot_ai.interface import Cards
from chatbot_ai.tools.models import DoctorCard, InvalidArgument, VisitCard, VisitStatus
from chatbot_ai.tools.ports import Ports

ToolKind = Literal["read", "propose"]
CARD_LIMIT = 3
SLOT_TEXT_LIMIT = 10
CARD_NOTE = "These options are shown to the member as cards. Name each option in your reply (doctor, clinic, date and time in UTC); the member books or confirms by clicking a card."


@dataclass(frozen=True)
class ToolOutcome:
    content: str
    cards: Cards | None = None


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(ToolArgs):
    pass


class SearchClinicsArgs(ToolArgs):
    location_id: int | None = Field(default=None, description="Catalog location id from list_locations")
    specialty_id: int | None = Field(default=None, description="Catalog specialty id from list_specialties")


class SearchDoctorsArgs(ToolArgs):
    clinic_id: int | None = None
    location_id: int | None = None
    specialty_id: int | None = None


class GetAvailabilityArgs(ToolArgs):
    doctor_id: int
    from_date: date | None = Field(default=None, description="First day to include, YYYY-MM-DD (UTC)")
    to_date: date | None = Field(default=None, description="Last day to include, YYYY-MM-DD (UTC)")


class RecommendDoctorsArgs(ToolArgs):
    specialty_id: int
    location_id: int | None = Field(default=None, description="Defaults to the member's home location")


class MyVisitsArgs(ToolArgs):
    status: VisitStatus | None = None


class ProposeCancelArgs(ToolArgs):
    visit_id: int | None = Field(default=None, description="Omit to offer every scheduled visit")


class Tool(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def kind(self) -> ToolKind: ...

    def definition(self) -> ChatCompletionToolParam: ...

    async def invoke(self, ports: Ports, arguments: str) -> ToolOutcome: ...


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def error_outcome(message: str) -> ToolOutcome:
    return ToolOutcome(content=_json({"error": message}))


@dataclass(frozen=True)
class TypedTool[ArgsT: ToolArgs]:
    name: str
    description: str
    kind: ToolKind
    args_model: type[ArgsT]
    handler: Callable[[Ports, ArgsT], Awaitable[ToolOutcome]]

    def definition(self) -> ChatCompletionToolParam:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.args_model.model_json_schema()},
        }

    async def invoke(self, ports: Ports, arguments: str) -> ToolOutcome:
        try:
            args = self.args_model.model_validate_json(arguments or "{}")
        except ValidationError as invalid:
            problems = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in invalid.errors())
            return error_outcome(f"invalid arguments for {self.name}: {problems}")
        try:
            return await self.handler(ports, args)
        except InvalidArgument as invalid:
            return error_outcome(str(invalid))


def _doctor_cards(cards: Sequence[DoctorCard]) -> Cards:
    return Cards(type="doctors", items=[c.model_dump() for c in cards])


def _visit_cards(card_type: str, cards: Sequence[VisitCard]) -> Cards:
    return Cards(type=card_type, items=[c.model_dump() for c in cards])


async def _list_locations(ports: Ports, args: NoArgs) -> ToolOutcome:
    return ToolOutcome(_json({"locations": [r.model_dump() for r in await ports.scheduling.list_locations()]}))


async def _list_specialties(ports: Ports, args: NoArgs) -> ToolOutcome:
    return ToolOutcome(_json({"specialties": [r.model_dump() for r in await ports.scheduling.list_specialties()]}))


async def _search_clinics(ports: Ports, args: SearchClinicsArgs) -> ToolOutcome:
    clinics = await ports.scheduling.search_clinics(args.location_id, args.specialty_id)
    return ToolOutcome(_json({"clinics": [c.model_dump() for c in clinics]}))


async def _search_doctors(ports: Ports, args: SearchDoctorsArgs) -> ToolOutcome:
    doctors = await ports.scheduling.search_doctors(args.clinic_id, args.location_id, args.specialty_id)
    return ToolOutcome(_json({"doctors": [d.model_dump() for d in doctors]}))


async def _get_availability(ports: Ports, args: GetAvailabilityArgs) -> ToolOutcome:
    slots = await ports.scheduling.available_slots(args.doctor_id, args.from_date, args.to_date, SLOT_TEXT_LIMIT)
    if not slots:
        return ToolOutcome(_json({"slots": [], "note": "No available slots in this window."}))
    shown = slots[:CARD_LIMIT]
    return ToolOutcome(
        _json({"shown_as_cards": [c.model_dump() for c in shown], "more_slot_times": [c.start_at for c in slots], "note": CARD_NOTE}),
        _doctor_cards(shown),
    )


async def _recommend_doctors(ports: Ports, args: RecommendDoctorsArgs) -> ToolOutcome:
    ranked = await ports.scheduling.recommend_doctors(args.specialty_id, args.location_id, CARD_LIMIT)
    if not ranked:
        return ToolOutcome(_json({"recommendations": [], "note": "No doctor of this specialty has an available slot."}))
    return ToolOutcome(
        _json({"shown_as_cards": [c.model_dump() for c in ranked], "note": CARD_NOTE + " Keep this order; it is already ranked."}),
        _doctor_cards(ranked),
    )


async def _my_visits(ports: Ports, args: MyVisitsArgs) -> ToolOutcome:
    return ToolOutcome(_json({"visits": [v.model_dump() for v in await ports.scheduling.my_visits(args.status)]}))


async def _propose_cancel(ports: Ports, args: ProposeCancelArgs) -> ToolOutcome:
    visits = await ports.scheduling.scheduled_visits(args.visit_id)
    if not visits:
        return ToolOutcome(_json({"scheduled_visits": [], "note": "There is no scheduled visit to cancel."}))
    return ToolOutcome(
        _json({"shown_as_cards": [v.model_dump() for v in visits], "note": CARD_NOTE}),
        _visit_cards("cancel_confirm", visits),
    )


async def _my_complaints(ports: Ports, args: NoArgs) -> ToolOutcome:
    return ToolOutcome(_json({"complaints": [c.model_dump() for c in await ports.complaints.my_complaints()]}))


async def _eligible_visits(ports: Ports, args: NoArgs) -> ToolOutcome:
    visits = await ports.complaints.eligible_visits()
    if not visits:
        return ToolOutcome(_json({"eligible_visits": [], "note": "No completed visit without a complaint."}))
    return ToolOutcome(
        _json({"shown_as_cards": [v.model_dump() for v in visits], "note": CARD_NOTE}),
        _visit_cards("visits_for_complaint", visits),
    )


SCHEDULING_TOOLS: tuple[Tool, ...] = (
    TypedTool("list_locations", "List the catalog locations with their ids.", "read", NoArgs, _list_locations),
    TypedTool("list_specialties", "List the medical specialties with their ids.", "read", NoArgs, _list_specialties),
    TypedTool("search_clinics", "Find clinics, optionally by location and specialty.", "read", SearchClinicsArgs, _search_clinics),
    TypedTool("search_doctors", "Find doctors by clinic, location or specialty.", "read", SearchDoctorsArgs, _search_doctors),
    TypedTool(
        "get_availability",
        "Available future slots of one doctor, earliest first, optionally within dates.",
        "propose",
        GetAvailabilityArgs,
        _get_availability,
    ),
    TypedTool(
        "recommend_doctors",
        "Recommend up to three doctors of a specialty, ranked by location and earliest available slot.",
        "propose",
        RecommendDoctorsArgs,
        _recommend_doctors,
    ),
    TypedTool("my_visits", "The member's own visits, optionally by status.", "read", MyVisitsArgs, _my_visits),
    TypedTool("propose_cancel", "Offer the member's scheduled visits as cancel cards.", "propose", ProposeCancelArgs, _propose_cancel),
)

COMPLAINT_TOOLS: tuple[Tool, ...] = (
    TypedTool("my_complaints", "The member's complaints with their status and the care team's replies.", "read", NoArgs, _my_complaints),
    TypedTool(
        "eligible_visits",
        "The member's completed visits without a complaint, offered as cards to file one.",
        "propose",
        NoArgs,
        _eligible_visits,
    ),
)
