from __future__ import annotations

from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Clinic, ClinicSpecialty, Doctor, Location, Specialty


def join_doctor_catalog[*Columns](query: Select[*Columns]) -> Select[*Columns]:
    return (
        query.join(ClinicSpecialty, ClinicSpecialty.id == Doctor.clinic_specialty_id)
        .join(Clinic, Clinic.id == ClinicSpecialty.clinic_id)
        .join(Specialty, Specialty.id == ClinicSpecialty.specialty_id)
        .join(Location, Location.id == Clinic.location_id)
    )


# Any: the counted statement may select any columns; only its rows are counted
async def count_rows(db: AsyncSession, query: Select[*tuple[Any, ...]]) -> int:
    result = await db.execute(select(func.count()).select_from(query.subquery()))
    return int(result.scalar_one())
