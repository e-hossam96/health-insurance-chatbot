from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.deps import Db, RequireAdmin
from backend.errors import api_error, not_found
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
from backend.queries import count_rows

router = APIRouter()


class NameCreate(BaseModel):
    name: str = Field(min_length=1)


class NamedOut(BaseModel):
    id: int
    name: str


class ClinicCreate(BaseModel):
    name: str = Field(min_length=1)
    location_id: int


class ClinicOut(BaseModel):
    id: int
    name: str
    location_id: int


class ClinicSpecialtyItem(BaseModel):
    specialty_id: int


class ClinicSpecialtyOut(BaseModel):
    id: int
    clinic_id: int
    specialty_id: int


class DoctorCreate(BaseModel):
    name: str = Field(min_length=1)
    clinic_specialty_id: int


class DoctorOut(BaseModel):
    id: int
    name: str
    clinic_specialty_id: int


def _has_history(message: str) -> HTTPException:
    return api_error("has_history", message, 409)


async def _create_unique_named[Model: (Location, Specialty)](db: Db, model: type[Model], name: str, label: str) -> NamedOut:
    existing = await db.execute(select(model).where(func.lower(model.name) == name.lower()))
    if existing.scalar_one_or_none() is not None:
        raise api_error("username_taken", f"{label} '{name}' already exists.", 409)
    row = model(name=name)
    db.add(row)
    await db.flush()
    await db.commit()
    return NamedOut(id=row.id, name=row.name)


@router.get("/locations")
async def list_locations(admin: RequireAdmin, db: Db) -> list[NamedOut]:
    result = await db.execute(select(Location).order_by(Location.name))
    return [NamedOut(id=r.id, name=r.name) for r in result.scalars()]


@router.post("/locations", status_code=201)
async def create_location(body: NameCreate, admin: RequireAdmin, db: Db) -> NamedOut:
    return await _create_unique_named(db, Location, body.name, "Location")


@router.delete("/locations/{location_id}")
async def delete_location(location_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    location = await db.get(Location, location_id)
    if location is None:
        raise not_found("Location not found.")
    profile_count = await count_rows(db, select(Profile.id).where(Profile.location_id == location_id))
    if profile_count > 0:
        raise _has_history(f"Location is used by {profile_count} profile(s).")
    clinic_count = await count_rows(db, select(Clinic.id).where(Clinic.location_id == location_id))
    await db.delete(location)
    await db.commit()
    return {"deleted": True, "cascade": {"clinics": clinic_count}}


@router.get("/specialties")
async def list_specialties(admin: RequireAdmin, db: Db) -> list[NamedOut]:
    result = await db.execute(select(Specialty).order_by(Specialty.name))
    return [NamedOut(id=r.id, name=r.name) for r in result.scalars()]


@router.post("/specialties", status_code=201)
async def create_specialty(body: NameCreate, admin: RequireAdmin, db: Db) -> NamedOut:
    return await _create_unique_named(db, Specialty, body.name, "Specialty")


@router.delete("/specialties/{specialty_id}")
async def delete_specialty(specialty_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    specialty = await db.get(Specialty, specialty_id)
    if specialty is None:
        raise not_found("Specialty not found.")
    link_count = await count_rows(db, select(ClinicSpecialty.id).where(ClinicSpecialty.specialty_id == specialty_id))
    if link_count > 0:
        raise _has_history(f"Specialty is linked to {link_count} clinic(s).")
    await db.delete(specialty)
    await db.commit()
    return {"deleted": True}


@router.get("/clinics")
async def list_clinics(admin: RequireAdmin, db: Db) -> list[ClinicOut]:
    result = await db.execute(select(Clinic).order_by(Clinic.name))
    return [ClinicOut(id=r.id, name=r.name, location_id=r.location_id) for r in result.scalars()]


@router.post("/clinics", status_code=201)
async def create_clinic(body: ClinicCreate, admin: RequireAdmin, db: Db) -> ClinicOut:
    if await db.get(Location, body.location_id) is None:
        raise not_found("Location not found.")
    clinic = Clinic(name=body.name, location_id=body.location_id)
    db.add(clinic)
    await db.flush()
    await db.commit()
    return ClinicOut(id=clinic.id, name=clinic.name, location_id=clinic.location_id)


@router.delete("/clinics/{clinic_id}")
async def delete_clinic(clinic_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    clinic = await db.get(Clinic, clinic_id)
    if clinic is None:
        raise not_found("Clinic not found.")
    visit_count = await count_rows(
        db,
        select(Visit.id)
        .join(Slot, Visit.slot_id == Slot.id)
        .join(Doctor, Slot.doctor_id == Doctor.id)
        .join(ClinicSpecialty, Doctor.clinic_specialty_id == ClinicSpecialty.id)
        .where(ClinicSpecialty.clinic_id == clinic_id),
    )
    if visit_count > 0:
        raise _has_history(f"Clinic has {visit_count} visit(s) in history.")
    link_count = await count_rows(db, select(ClinicSpecialty.id).where(ClinicSpecialty.clinic_id == clinic_id))
    doctor_count = await count_rows(
        db,
        select(Doctor.id)
        .join(ClinicSpecialty, Doctor.clinic_specialty_id == ClinicSpecialty.id)
        .where(ClinicSpecialty.clinic_id == clinic_id),
    )
    await db.delete(clinic)
    await db.commit()
    return {"deleted": True, "cascade": {"specialties": link_count, "doctors": doctor_count}}


@router.put("/clinics/{clinic_id}/specialties")
async def set_clinic_specialties(
    clinic_id: int,
    body: list[ClinicSpecialtyItem],
    admin: RequireAdmin,
    db: Db,
) -> list[ClinicSpecialtyOut]:
    if await db.get(Clinic, clinic_id) is None:
        raise not_found("Clinic not found.")

    wanted_ids = {item.specialty_id for item in body}
    current_links = list(
        (await db.execute(select(ClinicSpecialty).where(ClinicSpecialty.clinic_id == clinic_id))).scalars()
    )
    current_ids = {link.specialty_id for link in current_links}

    for link in current_links:
        if link.specialty_id in wanted_ids:
            continue
        if await count_rows(db, select(Doctor.id).where(Doctor.clinic_specialty_id == link.id)) > 0:
            raise _has_history(f"Cannot remove specialty {link.specialty_id}: has doctors.")
        await db.delete(link)

    for specialty_id in wanted_ids - current_ids:
        if await db.get(Specialty, specialty_id) is None:
            raise not_found(f"Specialty {specialty_id} not found.")
        db.add(ClinicSpecialty(clinic_id=clinic_id, specialty_id=specialty_id))

    await db.flush()
    await db.commit()

    result = await db.execute(select(ClinicSpecialty).where(ClinicSpecialty.clinic_id == clinic_id))
    return [
        ClinicSpecialtyOut(id=link.id, clinic_id=link.clinic_id, specialty_id=link.specialty_id)
        for link in result.scalars()
    ]


@router.get("/doctors")
async def list_doctors(admin: RequireAdmin, db: Db) -> list[DoctorOut]:
    result = await db.execute(select(Doctor).order_by(Doctor.name))
    return [DoctorOut(id=r.id, name=r.name, clinic_specialty_id=r.clinic_specialty_id) for r in result.scalars()]


@router.post("/doctors", status_code=201)
async def create_doctor(body: DoctorCreate, admin: RequireAdmin, db: Db) -> DoctorOut:
    if await db.get(ClinicSpecialty, body.clinic_specialty_id) is None:
        raise not_found("Clinic-specialty link not found.")
    doctor = Doctor(name=body.name, clinic_specialty_id=body.clinic_specialty_id)
    db.add(doctor)
    await db.flush()
    await db.commit()
    return DoctorOut(id=doctor.id, name=doctor.name, clinic_specialty_id=doctor.clinic_specialty_id)


@router.delete("/doctors/{doctor_id}")
async def delete_doctor(doctor_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    doctor = await db.get(Doctor, doctor_id)
    if doctor is None:
        raise not_found("Doctor not found.")
    visit_count = await count_rows(
        db, select(Visit.id).join(Slot, Visit.slot_id == Slot.id).where(Slot.doctor_id == doctor_id)
    )
    if visit_count > 0:
        raise _has_history(f"Doctor has {visit_count} visit(s) in history.")
    slot_count = await count_rows(db, select(Slot.id).where(Slot.doctor_id == doctor_id))
    await db.delete(doctor)
    await db.commit()
    return {"deleted": True, "cascade": {"slots": slot_count}}
