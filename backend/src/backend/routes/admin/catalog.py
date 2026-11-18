from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select

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


class LocationOut(BaseModel):
    id: int
    name: str
    clinic_count: int


class ClinicCreate(BaseModel):
    name: str = Field(min_length=1)
    location_id: int


class ClinicOut(BaseModel):
    id: int
    name: str
    location_id: int


class ClinicSpecialtyName(BaseModel):
    id: int
    name: str
    clinic_specialty_id: int


class ClinicListItem(BaseModel):
    id: int
    name: str
    location_id: int
    location_name: str
    specialties: list[ClinicSpecialtyName]


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


class DoctorListItem(BaseModel):
    id: int
    name: str
    clinic_specialty_id: int
    clinic_id: int
    clinic_name: str
    specialty_id: int
    specialty_name: str


class CascadePreview(BaseModel):
    cascade: dict[str, int]
    blocked: str | None


HISTORY_MESSAGE = "Can't delete: it has visit history."


def _has_history(message: str) -> HTTPException:
    return api_error("has_history", message, 409)


def _doctors_of_clinics(clinic_ids: Select[int]) -> Select[int]:
    return (
        select(Doctor.id)
        .join(ClinicSpecialty, Doctor.clinic_specialty_id == ClinicSpecialty.id)
        .where(ClinicSpecialty.clinic_id.in_(clinic_ids))
    )


def _slots_of_doctors(doctor_ids: Select[int]) -> Select[int]:
    return select(Slot.id).where(Slot.doctor_id.in_(doctor_ids))


def _visits_of_doctors(doctor_ids: Select[int]) -> Select[int]:
    return select(Visit.id).join(Slot, Visit.slot_id == Slot.id).where(Slot.doctor_id.in_(doctor_ids))


async def _location_preview(db: Db, location_id: int) -> CascadePreview:
    clinic_ids = select(Clinic.id).where(Clinic.location_id == location_id)
    doctor_ids = _doctors_of_clinics(clinic_ids)
    cascade = {
        "clinics": await count_rows(db, clinic_ids),
        "doctors": await count_rows(db, doctor_ids),
        "slots": await count_rows(db, _slots_of_doctors(doctor_ids)),
    }
    profile_count = await count_rows(db, select(Profile.id).where(Profile.location_id == location_id))
    blocked: str | None = None
    if profile_count > 0:
        blocked = f"Can't delete: {profile_count} member profile(s) use this location."
    elif await count_rows(db, _visits_of_doctors(doctor_ids)) > 0:
        blocked = HISTORY_MESSAGE
    return CascadePreview(cascade=cascade, blocked=blocked)


async def _specialty_preview(db: Db, specialty_id: int) -> CascadePreview:
    link_count = await count_rows(db, select(ClinicSpecialty.id).where(ClinicSpecialty.specialty_id == specialty_id))
    blocked = f"Can't delete: {link_count} clinic(s) offer this specialty." if link_count > 0 else None
    return CascadePreview(cascade={}, blocked=blocked)


async def _clinic_preview(db: Db, clinic_id: int) -> CascadePreview:
    clinic_ids = select(Clinic.id).where(Clinic.id == clinic_id)
    doctor_ids = _doctors_of_clinics(clinic_ids)
    cascade = {
        "specialties": await count_rows(db, select(ClinicSpecialty.id).where(ClinicSpecialty.clinic_id == clinic_id)),
        "doctors": await count_rows(db, doctor_ids),
        "slots": await count_rows(db, _slots_of_doctors(doctor_ids)),
    }
    blocked = HISTORY_MESSAGE if await count_rows(db, _visits_of_doctors(doctor_ids)) > 0 else None
    return CascadePreview(cascade=cascade, blocked=blocked)


async def _doctor_preview(db: Db, doctor_id: int) -> CascadePreview:
    doctor_ids = select(Doctor.id).where(Doctor.id == doctor_id)
    cascade = {"slots": await count_rows(db, _slots_of_doctors(doctor_ids))}
    blocked = HISTORY_MESSAGE if await count_rows(db, _visits_of_doctors(doctor_ids)) > 0 else None
    return CascadePreview(cascade=cascade, blocked=blocked)


async def _delete_after_preview(db: Db, row: object, preview: CascadePreview) -> dict[str, object]:
    if preview.blocked is not None:
        raise _has_history(preview.blocked)
    await db.delete(row)
    await db.commit()
    return {"deleted": True, "cascade": preview.cascade}


async def _create_unique_named[Model: (Location, Specialty)](db: Db, model: type[Model], name: str, label: str) -> NamedOut:
    existing = await db.execute(select(model).where(func.lower(model.name) == name.lower()))
    if existing.scalar_one_or_none() is not None:
        raise api_error("name_taken", f"{label} '{name}' already exists.", 409)
    row = model(name=name)
    db.add(row)
    await db.flush()
    await db.commit()
    return NamedOut(id=row.id, name=row.name)


@router.get("/locations")
async def list_locations(admin: RequireAdmin, db: Db) -> list[LocationOut]:
    clinic_count = select(func.count(Clinic.id)).where(Clinic.location_id == Location.id).scalar_subquery()
    result = await db.execute(select(Location.id, Location.name, clinic_count.label("clinic_count")).order_by(Location.name))
    return [LocationOut(id=row.id, name=row.name, clinic_count=row.clinic_count) for row in result]


@router.post("/locations", status_code=201)
async def create_location(body: NameCreate, admin: RequireAdmin, db: Db) -> NamedOut:
    return await _create_unique_named(db, Location, body.name, "Location")


@router.get("/locations/{location_id}/cascade")
async def preview_location_delete(location_id: int, admin: RequireAdmin, db: Db) -> CascadePreview:
    if await db.get(Location, location_id) is None:
        raise not_found("Location not found.")
    return await _location_preview(db, location_id)


@router.delete("/locations/{location_id}")
async def delete_location(location_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    location = await db.get(Location, location_id)
    if location is None:
        raise not_found("Location not found.")
    return await _delete_after_preview(db, location, await _location_preview(db, location_id))


@router.get("/specialties")
async def list_specialties(admin: RequireAdmin, db: Db) -> list[NamedOut]:
    result = await db.execute(select(Specialty).order_by(Specialty.name))
    return [NamedOut(id=r.id, name=r.name) for r in result.scalars()]


@router.post("/specialties", status_code=201)
async def create_specialty(body: NameCreate, admin: RequireAdmin, db: Db) -> NamedOut:
    return await _create_unique_named(db, Specialty, body.name, "Specialty")


@router.get("/specialties/{specialty_id}/cascade")
async def preview_specialty_delete(specialty_id: int, admin: RequireAdmin, db: Db) -> CascadePreview:
    if await db.get(Specialty, specialty_id) is None:
        raise not_found("Specialty not found.")
    return await _specialty_preview(db, specialty_id)


@router.delete("/specialties/{specialty_id}")
async def delete_specialty(specialty_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    specialty = await db.get(Specialty, specialty_id)
    if specialty is None:
        raise not_found("Specialty not found.")
    return await _delete_after_preview(db, specialty, await _specialty_preview(db, specialty_id))


@router.get("/clinics")
async def list_clinics(admin: RequireAdmin, db: Db) -> list[ClinicListItem]:
    clinics = await db.execute(
        select(Clinic.id, Clinic.name, Clinic.location_id, Location.name.label("location_name"))
        .join(Location, Location.id == Clinic.location_id)
        .order_by(Clinic.name)
    )
    links = await db.execute(
        select(ClinicSpecialty.clinic_id, ClinicSpecialty.id.label("link_id"), Specialty.id, Specialty.name)
        .join(Specialty, Specialty.id == ClinicSpecialty.specialty_id)
        .order_by(Specialty.name)
    )
    specialties_by_clinic: dict[int, list[ClinicSpecialtyName]] = {}
    for link in links:
        specialties_by_clinic.setdefault(link.clinic_id, []).append(
            ClinicSpecialtyName(id=link.id, name=link.name, clinic_specialty_id=link.link_id)
        )
    return [
        ClinicListItem(
            id=row.id,
            name=row.name,
            location_id=row.location_id,
            location_name=row.location_name,
            specialties=specialties_by_clinic.get(row.id, []),
        )
        for row in clinics
    ]


@router.post("/clinics", status_code=201)
async def create_clinic(body: ClinicCreate, admin: RequireAdmin, db: Db) -> ClinicOut:
    if await db.get(Location, body.location_id) is None:
        raise not_found("Location not found.")
    clinic = Clinic(name=body.name, location_id=body.location_id)
    db.add(clinic)
    await db.flush()
    await db.commit()
    return ClinicOut(id=clinic.id, name=clinic.name, location_id=clinic.location_id)


@router.get("/clinics/{clinic_id}/cascade")
async def preview_clinic_delete(clinic_id: int, admin: RequireAdmin, db: Db) -> CascadePreview:
    if await db.get(Clinic, clinic_id) is None:
        raise not_found("Clinic not found.")
    return await _clinic_preview(db, clinic_id)


@router.delete("/clinics/{clinic_id}")
async def delete_clinic(clinic_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    clinic = await db.get(Clinic, clinic_id)
    if clinic is None:
        raise not_found("Clinic not found.")
    return await _delete_after_preview(db, clinic, await _clinic_preview(db, clinic_id))


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
async def list_doctors(admin: RequireAdmin, db: Db) -> list[DoctorListItem]:
    result = await db.execute(
        select(
            Doctor.id,
            Doctor.name,
            Doctor.clinic_specialty_id,
            Clinic.id.label("clinic_id"),
            Clinic.name.label("clinic_name"),
            Specialty.id.label("specialty_id"),
            Specialty.name.label("specialty_name"),
        )
        .join(ClinicSpecialty, ClinicSpecialty.id == Doctor.clinic_specialty_id)
        .join(Clinic, Clinic.id == ClinicSpecialty.clinic_id)
        .join(Specialty, Specialty.id == ClinicSpecialty.specialty_id)
        .order_by(Doctor.name)
    )
    return [
        DoctorListItem(
            id=row.id,
            name=row.name,
            clinic_specialty_id=row.clinic_specialty_id,
            clinic_id=row.clinic_id,
            clinic_name=row.clinic_name,
            specialty_id=row.specialty_id,
            specialty_name=row.specialty_name,
        )
        for row in result
    ]


@router.post("/doctors", status_code=201)
async def create_doctor(body: DoctorCreate, admin: RequireAdmin, db: Db) -> DoctorOut:
    if await db.get(ClinicSpecialty, body.clinic_specialty_id) is None:
        raise not_found("Clinic-specialty link not found.")
    doctor = Doctor(name=body.name, clinic_specialty_id=body.clinic_specialty_id)
    db.add(doctor)
    await db.flush()
    await db.commit()
    return DoctorOut(id=doctor.id, name=doctor.name, clinic_specialty_id=doctor.clinic_specialty_id)


@router.get("/doctors/{doctor_id}/cascade")
async def preview_doctor_delete(doctor_id: int, admin: RequireAdmin, db: Db) -> CascadePreview:
    if await db.get(Doctor, doctor_id) is None:
        raise not_found("Doctor not found.")
    return await _doctor_preview(db, doctor_id)


@router.delete("/doctors/{doctor_id}")
async def delete_doctor(doctor_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    doctor = await db.get(Doctor, doctor_id)
    if doctor is None:
        raise not_found("Doctor not found.")
    return await _delete_after_preview(db, doctor, await _doctor_preview(db, doctor_id))
