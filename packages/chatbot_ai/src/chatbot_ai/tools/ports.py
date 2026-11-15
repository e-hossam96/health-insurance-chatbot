from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from chatbot_ai.tools.models import (
    ClinicInfo,
    ComplaintInfo,
    DoctorCard,
    DoctorInfo,
    NamedRef,
    VisitCard,
    VisitInfo,
    VisitStatus,
)


@runtime_checkable
class SchedulingPort(Protocol):
    async def list_locations(self) -> list[NamedRef]: ...

    async def list_specialties(self) -> list[NamedRef]: ...

    async def search_clinics(self, location_id: int | None, specialty_id: int | None) -> list[ClinicInfo]: ...

    async def search_doctors(
        self, clinic_id: int | None, location_id: int | None, specialty_id: int | None
    ) -> list[DoctorInfo]: ...

    async def available_slots(
        self, doctor_id: int, from_date: date | None, to_date: date | None, limit: int
    ) -> list[DoctorCard]: ...

    async def recommend_doctors(self, specialty_id: int, location_id: int | None, limit: int) -> list[DoctorCard]: ...

    async def my_visits(self, status: VisitStatus | None) -> list[VisitInfo]: ...

    async def scheduled_visits(self, visit_id: int | None) -> list[VisitCard]: ...


@runtime_checkable
class ComplaintsPort(Protocol):
    async def my_complaints(self) -> list[ComplaintInfo]: ...

    async def eligible_visits(self) -> list[VisitCard]: ...


@dataclass(frozen=True)
class Ports:
    scheduling: SchedulingPort
    complaints: ComplaintsPort
