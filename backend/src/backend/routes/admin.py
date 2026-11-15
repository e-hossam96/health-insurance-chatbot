"""Admin routes (requires admin role + admin mode)."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import extract, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.deps import ClockDep, CurrentSession, Db, RequireAdmin
from backend.models import (
    Clinic,
    ClinicSpecialty,
    Complaint,
    ComplaintReply,
    ComplaintStatus,
    Doctor,
    Location,
    Profile,
    Slot,
    SlotStatus,
    Specialty,
    Visit,
    VisitStatus,
)

SLOT_START_HOUR = 9
SLOT_END_HOUR = 16

router = APIRouter(prefix="/admin", tags=["admin"])


def _error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": message}},
    )


# --- Locations ---


class LocationCreate(BaseModel):
    name: str = Field(min_length=1)


class LocationOut(BaseModel):
    id: int
    name: str


@router.get("/locations")
async def list_locations(admin: RequireAdmin, db: Db) -> list[LocationOut]:
    result = await db.execute(select(Location).order_by(Location.name))
    return [LocationOut(id=r.id, name=r.name) for r in result.scalars()]


@router.post("/locations", status_code=201)
async def create_location(
    body: LocationCreate, admin: RequireAdmin, db: Db
) -> LocationOut:
    existing = await db.execute(
        select(Location).where(func.lower(Location.name) == body.name.lower())
    )
    if existing.scalar_one_or_none() is not None:
        raise _error("username_taken", f"Location '{body.name}' already exists.", 409)
    loc = Location(name=body.name)
    db.add(loc)
    await db.flush()
    await db.commit()
    return LocationOut(id=loc.id, name=loc.name)


@router.delete("/locations/{location_id}")
async def delete_location(
    location_id: int, admin: RequireAdmin, db: Db
) -> dict[str, object]:
    loc = await db.get(Location, location_id)
    if loc is None:
        raise _error("not_found", "Location not found.", 404)

    profile_count_result = await db.execute(
        select(func.count()).select_from(Profile).where(Profile.location_id == location_id)
    )
    profile_count: int = profile_count_result.scalar_one()
    if profile_count > 0:
        raise _error("has_history", f"Location is used by {profile_count} profile(s).", 409)

    clinic_count_result = await db.execute(
        select(func.count()).select_from(Clinic).where(Clinic.location_id == location_id)
    )
    clinic_count: int = clinic_count_result.scalar_one()

    await db.delete(loc)
    await db.commit()
    return {"deleted": True, "cascade": {"clinics": clinic_count}}


# --- Specialties ---


class SpecialtyCreate(BaseModel):
    name: str = Field(min_length=1)


class SpecialtyOut(BaseModel):
    id: int
    name: str


@router.get("/specialties")
async def list_specialties(admin: RequireAdmin, db: Db) -> list[SpecialtyOut]:
    result = await db.execute(select(Specialty).order_by(Specialty.name))
    return [SpecialtyOut(id=r.id, name=r.name) for r in result.scalars()]


@router.post("/specialties", status_code=201)
async def create_specialty(
    body: SpecialtyCreate, admin: RequireAdmin, db: Db
) -> SpecialtyOut:
    existing = await db.execute(
        select(Specialty).where(func.lower(Specialty.name) == body.name.lower())
    )
    if existing.scalar_one_or_none() is not None:
        raise _error("username_taken", f"Specialty '{body.name}' already exists.", 409)
    spec = Specialty(name=body.name)
    db.add(spec)
    await db.flush()
    await db.commit()
    return SpecialtyOut(id=spec.id, name=spec.name)


@router.delete("/specialties/{specialty_id}")
async def delete_specialty(
    specialty_id: int, admin: RequireAdmin, db: Db
) -> dict[str, object]:
    spec = await db.get(Specialty, specialty_id)
    if spec is None:
        raise _error("not_found", "Specialty not found.", 404)

    cs_count_result = await db.execute(
        select(func.count()).select_from(ClinicSpecialty).where(
            ClinicSpecialty.specialty_id == specialty_id
        )
    )
    cs_count: int = cs_count_result.scalar_one()
    if cs_count > 0:
        raise _error("has_history", f"Specialty is linked to {cs_count} clinic(s).", 409)

    await db.delete(spec)
    await db.commit()
    return {"deleted": True}


# --- Clinics ---


class ClinicCreate(BaseModel):
    name: str = Field(min_length=1)
    location_id: int


class ClinicOut(BaseModel):
    id: int
    name: str
    location_id: int


@router.get("/clinics")
async def list_clinics(admin: RequireAdmin, db: Db) -> list[ClinicOut]:
    result = await db.execute(select(Clinic).order_by(Clinic.name))
    return [ClinicOut(id=r.id, name=r.name, location_id=r.location_id) for r in result.scalars()]


@router.post("/clinics", status_code=201)
async def create_clinic(
    body: ClinicCreate, admin: RequireAdmin, db: Db
) -> ClinicOut:
    loc = await db.get(Location, body.location_id)
    if loc is None:
        raise _error("not_found", "Location not found.", 404)
    clinic = Clinic(name=body.name, location_id=body.location_id)
    db.add(clinic)
    await db.flush()
    await db.commit()
    return ClinicOut(id=clinic.id, name=clinic.name, location_id=clinic.location_id)


@router.delete("/clinics/{clinic_id}")
async def delete_clinic(
    clinic_id: int, admin: RequireAdmin, db: Db
) -> dict[str, object]:
    clinic = await db.get(Clinic, clinic_id)
    if clinic is None:
        raise _error("not_found", "Clinic not found.", 404)

    visit_count_result = await db.execute(
        select(func.count()).select_from(Visit)
        .join(Slot, Visit.slot_id == Slot.id)
        .join(Doctor, Slot.doctor_id == Doctor.id)
        .join(ClinicSpecialty, Doctor.clinic_specialty_id == ClinicSpecialty.id)
        .where(ClinicSpecialty.clinic_id == clinic_id)
    )
    visit_count: int = visit_count_result.scalar_one()
    if visit_count > 0:
        raise _error("has_history", f"Clinic has {visit_count} visit(s) in history.", 409)

    cs_count_result = await db.execute(
        select(func.count()).select_from(ClinicSpecialty).where(
            ClinicSpecialty.clinic_id == clinic_id
        )
    )
    cs_count: int = cs_count_result.scalar_one()

    doctor_count_result = await db.execute(
        select(func.count()).select_from(Doctor)
        .join(ClinicSpecialty, Doctor.clinic_specialty_id == ClinicSpecialty.id)
        .where(ClinicSpecialty.clinic_id == clinic_id)
    )
    doctor_count: int = doctor_count_result.scalar_one()

    await db.delete(clinic)
    await db.commit()
    return {"deleted": True, "cascade": {"specialties": cs_count, "doctors": doctor_count}}


# --- Clinic specialties ---


class ClinicSpecialtyItem(BaseModel):
    specialty_id: int


class ClinicSpecialtyOut(BaseModel):
    id: int
    clinic_id: int
    specialty_id: int


@router.put("/clinics/{clinic_id}/specialties")
async def set_clinic_specialties(
    clinic_id: int,
    body: list[ClinicSpecialtyItem],
    admin: RequireAdmin,
    db: Db,
) -> list[ClinicSpecialtyOut]:
    clinic = await db.get(Clinic, clinic_id)
    if clinic is None:
        raise _error("not_found", "Clinic not found.", 404)

    wanted_ids = {item.specialty_id for item in body}

    existing_result = await db.execute(
        select(ClinicSpecialty).where(ClinicSpecialty.clinic_id == clinic_id)
    )
    existing = list(existing_result.scalars())
    existing_map = {cs.specialty_id: cs for cs in existing}

    for cs in existing:
        if cs.specialty_id not in wanted_ids:
            doctor_count_result = await db.execute(
                select(func.count()).select_from(Doctor).where(
                    Doctor.clinic_specialty_id == cs.id
                )
            )
            if doctor_count_result.scalar_one() > 0:
                raise _error(
                    "has_history",
                    f"Cannot remove specialty {cs.specialty_id}: has doctors.",
                    409,
                )
            await db.delete(cs)

    for sid in wanted_ids:
        if sid not in existing_map:
            spec = await db.get(Specialty, sid)
            if spec is None:
                raise _error("not_found", f"Specialty {sid} not found.", 404)
            db.add(ClinicSpecialty(clinic_id=clinic_id, specialty_id=sid))

    await db.flush()
    await db.commit()

    result = await db.execute(
        select(ClinicSpecialty).where(ClinicSpecialty.clinic_id == clinic_id)
    )
    return [
        ClinicSpecialtyOut(id=cs.id, clinic_id=cs.clinic_id, specialty_id=cs.specialty_id)
        for cs in result.scalars()
    ]


# --- Doctors ---


class DoctorCreate(BaseModel):
    name: str = Field(min_length=1)
    clinic_specialty_id: int


class DoctorOut(BaseModel):
    id: int
    name: str
    clinic_specialty_id: int


@router.get("/doctors")
async def list_doctors(admin: RequireAdmin, db: Db) -> list[DoctorOut]:
    result = await db.execute(select(Doctor).order_by(Doctor.name))
    return [
        DoctorOut(id=r.id, name=r.name, clinic_specialty_id=r.clinic_specialty_id)
        for r in result.scalars()
    ]


@router.post("/doctors", status_code=201)
async def create_doctor(
    body: DoctorCreate, admin: RequireAdmin, db: Db
) -> DoctorOut:
    cs = await db.get(ClinicSpecialty, body.clinic_specialty_id)
    if cs is None:
        raise _error("not_found", "Clinic-specialty link not found.", 404)
    doctor = Doctor(name=body.name, clinic_specialty_id=body.clinic_specialty_id)
    db.add(doctor)
    await db.flush()
    await db.commit()
    return DoctorOut(id=doctor.id, name=doctor.name, clinic_specialty_id=doctor.clinic_specialty_id)


@router.delete("/doctors/{doctor_id}")
async def delete_doctor(
    doctor_id: int, admin: RequireAdmin, db: Db
) -> dict[str, object]:
    doctor = await db.get(Doctor, doctor_id)
    if doctor is None:
        raise _error("not_found", "Doctor not found.", 404)

    visit_count_result = await db.execute(
        select(func.count()).select_from(Visit)
        .join(Slot, Visit.slot_id == Slot.id)
        .where(Slot.doctor_id == doctor_id)
    )
    visit_count: int = visit_count_result.scalar_one()
    if visit_count > 0:
        raise _error("has_history", f"Doctor has {visit_count} visit(s) in history.", 409)

    slot_count_result = await db.execute(
        select(func.count()).select_from(Slot).where(Slot.doctor_id == doctor_id)
    )
    slot_count: int = slot_count_result.scalar_one()

    await db.delete(doctor)
    await db.commit()
    return {"deleted": True, "cascade": {"slots": slot_count}}


# --- Slots ---


class SlotCreate(BaseModel):
    doctor_id: int
    start_at: datetime


class SlotOut(BaseModel):
    id: int
    doctor_id: int
    start_at: datetime
    status: str


def _validate_slot_time(start_at: datetime) -> None:
    utc_dt = start_at.astimezone(UTC)
    if utc_dt.minute != 0 or utc_dt.second != 0 or utc_dt.microsecond != 0:
        raise _error("invalid_time", "Slot must start on the hour.", 422)
    if utc_dt.hour < SLOT_START_HOUR or utc_dt.hour > SLOT_END_HOUR:
        raise _error(
            "invalid_time",
            f"Slot must be within working hours ({SLOT_START_HOUR}:00-{SLOT_END_HOUR + 1}:00 UTC).",
            422,
        )


@router.get("/slots")
async def list_slots(
    admin: RequireAdmin,
    db: Db,
    doctor_id: int = Query(...),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
) -> list[SlotOut]:
    result = await db.execute(
        select(Slot)
        .where(
            Slot.doctor_id == doctor_id,
            extract("year", Slot.start_at) == year,
            extract("month", Slot.start_at) == month,
        )
        .order_by(Slot.start_at)
    )
    return [
        SlotOut(id=s.id, doctor_id=s.doctor_id, start_at=s.start_at, status=s.status.value)
        for s in result.scalars()
    ]


@router.post("/slots", status_code=201)
async def create_slot(body: SlotCreate, admin: RequireAdmin, db: Db) -> SlotOut:
    _validate_slot_time(body.start_at)

    doctor = await db.get(Doctor, body.doctor_id)
    if doctor is None:
        raise _error("not_found", "Doctor not found.", 404)

    existing = await db.execute(
        select(Slot).where(
            Slot.doctor_id == body.doctor_id,
            Slot.start_at == body.start_at,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise _error("duplicate", "Duplicate slot for this doctor and time.", 409)

    slot = Slot(doctor_id=body.doctor_id, start_at=body.start_at)
    db.add(slot)
    await db.flush()
    await db.commit()
    return SlotOut(
        id=slot.id, doctor_id=slot.doctor_id, start_at=slot.start_at, status=slot.status.value
    )


@router.delete("/slots/{slot_id}")
async def delete_slot(
    slot_id: int, admin: RequireAdmin, db: Db
) -> dict[str, object]:
    slot = await db.get(Slot, slot_id)
    if slot is None:
        raise _error("not_found", "Slot not found.", 404)
    if slot.status != SlotStatus.available:
        raise _error("slot_booked", "Cannot remove a booked slot.", 409)
    await db.delete(slot)
    await db.commit()
    return {"deleted": True}


# --- Auto-fill ---


class AutofillRequest(BaseModel):
    doctor_id: int


class AutofillResponse(BaseModel):
    created: int
    message: str


@router.post("/slots/autofill")
async def autofill_slots(
    body: AutofillRequest, admin: RequireAdmin, db: Db, clock: ClockDep
) -> AutofillResponse:
    doctor = await db.get(Doctor, body.doctor_id)
    if doctor is None:
        raise _error("not_found", "Doctor not found.", 404)

    now = clock.now().astimezone(UTC)
    today = now.date()
    last_day = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])

    rows: list[dict[str, int | datetime]] = []
    current = today
    while current <= last_day:
        for hour in range(SLOT_START_HOUR, SLOT_END_HOUR + 1):
            slot_dt = datetime(current.year, current.month, current.day, hour, 0, tzinfo=UTC)
            if slot_dt < now:
                continue
            rows.append({"doctor_id": body.doctor_id, "start_at": slot_dt})
        current += timedelta(days=1)

    if not rows:
        return AutofillResponse(created=0, message="Nothing to create")

    stmt = pg_insert(Slot).values(rows).on_conflict_do_nothing(
        index_elements=["doctor_id", "start_at"]
    )
    result = await db.execute(stmt)
    await db.commit()
    created = int(result.rowcount)  # type: ignore[attr-defined]

    if created == 0:
        return AutofillResponse(created=0, message="Nothing to create")
    return AutofillResponse(created=created, message=f"Created {created} slot(s)")


# --- Visit completion (D3) ---


class VisitStatusOut(BaseModel):
    id: int
    status: str


@router.post("/visits/{visit_id}/complete")
async def complete_visit(
    visit_id: int, admin: RequireAdmin, db: Db
) -> VisitStatusOut:
    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise _error("not_found", "Visit not found.", 404)
    if visit.status != VisitStatus.scheduled:
        raise _error(
            "invalid_transition",
            f"Cannot complete a visit with status '{visit.status.value}'.",
            409,
        )
    visit.status = VisitStatus.completed
    await db.commit()
    return VisitStatusOut(id=visit.id, status=visit.status.value)


# --- Complaints (E3, E4, E5, B7) ---


class ReplyCreate(BaseModel):
    body: str = Field(min_length=1)


class ReplyOut(BaseModel):
    id: int
    complaint_id: int
    admin_account_id: int
    body: str


@router.post("/complaints/{complaint_id}/reply", status_code=201)
async def reply_to_complaint(
    complaint_id: int,
    body: ReplyCreate,
    admin: RequireAdmin,
    session: CurrentSession,
    db: Db,
) -> ReplyOut:
    complaint = await db.get(Complaint, complaint_id)
    if complaint is None:
        raise _error("not_found", "Complaint not found.", 404)

    # E5: replies on closed complaint rejected
    if complaint.status == ComplaintStatus.closed:
        raise _error("complaint_closed", "Cannot reply to a closed complaint.", 409)

    # B7: admin_account_id references an admin role (enforced by RequireAdmin dep)
    reply = ComplaintReply(
        complaint_id=complaint_id,
        admin_account_id=session.account_id,
        body=body.body,
    )
    db.add(reply)
    await db.flush()
    await db.commit()

    # E4: reply does NOT change status
    return ReplyOut(
        id=reply.id, complaint_id=reply.complaint_id,
        admin_account_id=reply.admin_account_id, body=reply.body,
    )


@router.post("/complaints/{complaint_id}/close")
async def close_complaint(
    complaint_id: int, admin: RequireAdmin, db: Db
) -> dict[str, object]:
    complaint = await db.get(Complaint, complaint_id)
    if complaint is None:
        raise _error("not_found", "Complaint not found.", 404)
    if complaint.status == ComplaintStatus.closed:
        raise _error("complaint_closed", "Complaint is already closed.", 409)
    complaint.status = ComplaintStatus.closed
    await db.commit()
    return {"id": complaint.id, "status": complaint.status.value}


# --- Admin lists (D4) ---


@router.get("/visits")
async def admin_list_visits(
    admin: RequireAdmin,
    db: Db,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> dict[str, object]:
    base = select(Visit)
    count_base = select(func.count()).select_from(Visit)
    if status is not None:
        base = base.where(Visit.status == status)
        count_base = count_base.where(Visit.status == status)

    total_result = await db.execute(count_base)
    total: int = total_result.scalar_one()

    result = await db.execute(
        base.join(Slot, Visit.slot_id == Slot.id)
        .order_by(Slot.start_at.desc())
        .limit(limit)
        .offset(offset)
    )
    visits = list(result.scalars())
    items = [
        {"id": v.id, "profile_id": v.profile_id, "slot_id": v.slot_id, "status": v.status.value}
        for v in visits
    ]
    return {"items": items, "total": total}


@router.get("/complaints")
async def admin_list_complaints(
    admin: RequireAdmin,
    db: Db,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> dict[str, object]:
    base = select(Complaint)
    count_base = select(func.count()).select_from(Complaint)
    if status is not None:
        base = base.where(Complaint.status == status)
        count_base = count_base.where(Complaint.status == status)

    total_result = await db.execute(count_base)
    total: int = total_result.scalar_one()

    result = await db.execute(
        base.order_by(Complaint.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    complaints = list(result.scalars())
    items = [
        {"id": c.id, "visit_id": c.visit_id, "description": c.description, "status": c.status.value}
        for c in complaints
    ]
    return {"items": items, "total": total}


# --- KB placeholder ---


@router.get("/kb")
async def list_kb(admin: RequireAdmin, db: Db) -> dict[str, object]:
    return {"items": [], "total": 0}
