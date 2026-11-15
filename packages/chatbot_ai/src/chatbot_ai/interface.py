from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# --- Turn request ---


@dataclass(frozen=True)
class ProfileInfo:
    display_name: str
    location_name: str
    location_id: int


@dataclass(frozen=True)
class HistoryRow:
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class TurnRequest:
    history: list[HistoryRow]
    message: str
    profile: ProfileInfo
    needs_label: bool
    session_id: int


# --- Turn events ---


@dataclass(frozen=True)
class Intent:
    code: str


@dataclass(frozen=True)
class Token:
    text: str
    elapsed: float


@dataclass(frozen=True)
class Cards:
    type: str
    items: list[dict[str, Any]]


@dataclass(frozen=True)
class Timings:
    classify: float = 0.0
    rewrite: float = 0.0
    embed: float = 0.0
    search: float = 0.0
    rerank: float = 0.0
    ttft: float = 0.0
    generate: float = 0.0
    total: float = 0.0
    tool_calls: list[tuple[str, float]] = field(default_factory=list)


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class Done:
    new_rows: list[HistoryRow]
    timings: Timings = field(default_factory=Timings)
    usage: Usage = field(default_factory=Usage)


TurnEvent = Intent | Token | Cards | Done

TurnRunner = Callable[["TurnRequest"], AsyncIterator[TurnEvent]]


# --- Ports ---


@runtime_checkable
class SchedulingPort(Protocol):
    async def list_locations(self) -> list[dict[str, Any]]: ...
    async def list_specialties(self) -> list[dict[str, Any]]: ...
    async def search_clinics(
        self,
        location_id: int | None = None,
        specialty_id: int | None = None,
    ) -> list[dict[str, Any]]: ...
    async def search_doctors(
        self,
        clinic_id: int | None = None,
        location_id: int | None = None,
        specialty_id: int | None = None,
    ) -> list[dict[str, Any]]: ...
    async def get_availability(
        self,
        doctor_id: int,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]: ...
    async def my_visits(self, status: str | None = None) -> list[dict[str, Any]]: ...
    async def recommend_doctors(
        self,
        specialty_id: int,
        location_id: int | None = None,
    ) -> dict[str, Any]: ...
    async def propose_cancel(self, visit_id: int | None = None) -> dict[str, Any]: ...


@runtime_checkable
class ComplaintsPort(Protocol):
    async def my_complaints(self) -> list[dict[str, Any]]: ...
    async def eligible_visits(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Ports:
    scheduling: SchedulingPort
    complaints: ComplaintsPort
