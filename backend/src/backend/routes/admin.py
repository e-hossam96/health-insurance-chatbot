"""Admin routes (requires admin role + admin mode)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.deps import Db, RequireAdmin
from backend.models import (
    Clinic,
    ClinicSpecialty,
    Doctor,
    Location,
    Profile,
    Slot,
    Specialty,
    Visit,
)

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


# --- KB placeholder ---


@router.get("/kb")
async def list_kb(admin: RequireAdmin, db: Db) -> dict[str, object]:
    return {"items": [], "total": 0}
