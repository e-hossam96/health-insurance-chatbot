from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

VisitStatus = Literal["scheduled", "completed", "cancelled"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class NamedRef(_Frozen):
    id: int
    name: str


class ClinicInfo(_Frozen):
    id: int
    name: str
    location_id: int
    location: str
    specialties: list[str]


class DoctorInfo(_Frozen):
    id: int
    name: str
    specialty_id: int
    specialty: str
    clinic_id: int
    clinic: str
    location: str


class DoctorCard(_Frozen):
    slot_id: int
    doctor_name: str
    specialty: str
    clinic: str
    location: str
    start_at: str


class VisitCard(_Frozen):
    visit_id: int
    start_at: str
    doctor_name: str
    specialty: str
    clinic: str


class VisitInfo(VisitCard):
    status: VisitStatus


class ComplaintInfo(_Frozen):
    id: int
    visit_id: int
    description: str
    status: Literal["open", "closed"]
    replies: list[str]


class InvalidArgument(ValueError):
    pass
