from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from backend.deps import Db, RequireAdmin
from backend.errors import api_error, not_found
from backend.models import (
    Clinic,
    Doctor,
    Location,
    Profile,
    Slot,
    Specialty,
    Visit,
    VisitStatus,
)
from backend.queries import count_rows, join_doctor_catalog

router = APIRouter()


class VisitStatusOut(BaseModel):
    id: int
    status: str


class AdminVisitItem(BaseModel):
    id: int
    profile_id: int
    slot_id: int
    status: str
    patient_name: str
    location: str
    clinic: str
    specialty: str
    doctor_name: str
    start_at: str


class AdminVisitList(BaseModel):
    items: list[AdminVisitItem]
    total: int


@router.post("/visits/{visit_id}/complete")
async def complete_visit(visit_id: int, admin: RequireAdmin, db: Db) -> VisitStatusOut:
    visit = await db.get(Visit, visit_id, with_for_update=True)
    if visit is None:
        raise not_found("Visit not found.")
    # D3
    if visit.status != VisitStatus.scheduled:
        raise api_error("invalid_transition", f"Cannot complete a visit with status '{visit.status.value}'.", 409)
    visit.status = VisitStatus.completed
    await db.commit()
    return VisitStatusOut(id=visit.id, status=visit.status.value)


@router.get("/visits")
async def admin_list_visits(
    admin: RequireAdmin,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: VisitStatus | None = None,
    patient: str | None = None,
    visit_id: int | None = None,
) -> AdminVisitList:
    # D4: every name comes from joins
    query = join_doctor_catalog(
        select(
            Visit.id,
            Visit.profile_id,
            Visit.slot_id,
            Visit.status,
            Profile.name.label("patient_name"),
            Location.name.label("location"),
            Clinic.name.label("clinic"),
            Specialty.name.label("specialty"),
            Doctor.name.label("doctor_name"),
            Slot.start_at,
        )
        .join(Profile, Profile.id == Visit.profile_id)
        .join(Slot, Visit.slot_id == Slot.id)
        .join(Doctor, Slot.doctor_id == Doctor.id)
    )
    if status is not None:
        query = query.where(Visit.status == status)
    if patient:
        query = query.where(func.lower(Profile.name).contains(patient.strip().lower(), autoescape=True))
    if visit_id is not None:
        query = query.where(Visit.id == visit_id)
    total = await count_rows(db, query)
    rows = await db.execute(query.order_by(Slot.start_at.desc(), Visit.id.desc()).limit(limit).offset(offset))
    return AdminVisitList(
        items=[
            AdminVisitItem(
                id=row.id,
                profile_id=row.profile_id,
                slot_id=row.slot_id,
                status=row.status.value,
                patient_name=row.patient_name,
                location=row.location,
                clinic=row.clinic,
                specialty=row.specialty,
                doctor_name=row.doctor_name,
                start_at=row.start_at.isoformat(),
            )
            for row in rows
        ],
        total=total,
    )
