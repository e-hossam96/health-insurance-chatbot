from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import extract, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.deps import ClockDep, Db, RequireAdmin
from backend.errors import api_error, not_found
from backend.models import Doctor, Slot, SlotStatus, Visit, VisitStatus

SLOT_START_HOUR = 9
SLOT_END_HOUR = 16

router = APIRouter()


class SlotCreate(BaseModel):
    doctor_id: int
    start_at: datetime


class SlotOut(BaseModel):
    id: int
    doctor_id: int
    start_at: datetime
    status: str
    visit_id: int | None = None

    @classmethod
    def from_row(cls, slot: Slot, visit_id: int | None = None) -> SlotOut:
        return cls(id=slot.id, doctor_id=slot.doctor_id, start_at=slot.start_at, status=slot.status.value, visit_id=visit_id)


class AutofillRequest(BaseModel):
    doctor_id: int


class AutofillResponse(BaseModel):
    created: int
    skipped: int
    message: str


def validate_slot_time(start_at: datetime) -> None:
    utc_dt = start_at.astimezone(UTC)
    if utc_dt.minute != 0 or utc_dt.second != 0 or utc_dt.microsecond != 0:
        raise api_error("invalid_time", "Slot must start on the hour.", 422)
    if utc_dt.hour < SLOT_START_HOUR or utc_dt.hour > SLOT_END_HOUR:
        raise api_error(
            "invalid_time",
            f"Slot must be within working hours ({SLOT_START_HOUR}:00-{SLOT_END_HOUR + 1}:00 UTC).",
            422,
        )


def remaining_slot_times_this_month(now: datetime) -> list[datetime]:
    now = now.astimezone(UTC)
    today = now.date()
    last_day = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    times: list[datetime] = []
    day = today
    while day <= last_day:
        for hour in range(SLOT_START_HOUR, SLOT_END_HOUR + 1):
            start_at = datetime(day.year, day.month, day.day, hour, tzinfo=UTC)
            if start_at >= now:
                times.append(start_at)
        day += timedelta(days=1)
    return times


async def _require_doctor(db: Db, doctor_id: int) -> None:
    if await db.get(Doctor, doctor_id) is None:
        raise not_found("Doctor not found.")


@router.get("/slots")
async def list_slots(
    admin: RequireAdmin,
    db: Db,
    doctor_id: int = Query(...),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
) -> list[SlotOut]:
    result = await db.execute(
        select(Slot, Visit.id)
        .outerjoin(Visit, (Visit.slot_id == Slot.id) & (Visit.status != VisitStatus.cancelled))
        .where(
            Slot.doctor_id == doctor_id,
            extract("year", Slot.start_at) == year,
            extract("month", Slot.start_at) == month,
        )
        .order_by(Slot.start_at)
    )
    return [SlotOut.from_row(slot, visit_id) for slot, visit_id in result.all()]


@router.post("/slots", status_code=201)
async def create_slot(body: SlotCreate, admin: RequireAdmin, db: Db) -> SlotOut:
    validate_slot_time(body.start_at)
    await _require_doctor(db, body.doctor_id)

    existing = await db.execute(select(Slot).where(Slot.doctor_id == body.doctor_id, Slot.start_at == body.start_at))
    if existing.scalar_one_or_none() is not None:
        raise api_error("duplicate", "Duplicate slot for this doctor and time.", 409)

    slot = Slot(doctor_id=body.doctor_id, start_at=body.start_at)
    db.add(slot)
    await db.flush()
    await db.commit()
    return SlotOut.from_row(slot)


@router.delete("/slots/{slot_id}")
async def delete_slot(slot_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    slot = await db.get(Slot, slot_id)
    if slot is None:
        raise not_found("Slot not found.")
    if slot.status != SlotStatus.available:
        raise api_error("slot_booked", "This slot is booked. Cancel the visit first.", 409)
    await db.delete(slot)
    await db.commit()
    return {"deleted": True}


@router.post("/slots/autofill")
async def autofill_slots(body: AutofillRequest, admin: RequireAdmin, db: Db, clock: ClockDep) -> AutofillResponse:
    await _require_doctor(db, body.doctor_id)

    rows = [{"doctor_id": body.doctor_id, "start_at": start_at} for start_at in remaining_slot_times_this_month(clock.now())]
    created = 0
    if rows:
        statement = pg_insert(Slot).values(rows).on_conflict_do_nothing(index_elements=["doctor_id", "start_at"])
        result = await db.execute(statement)
        await db.commit()
        created = int(result.rowcount)  # type: ignore[attr-defined]

    skipped = len(rows) - created
    if created == 0:
        return AutofillResponse(created=0, skipped=skipped, message="Nothing to create")
    return AutofillResponse(
        created=created,
        skipped=skipped,
        message=f"Created {created} {_slots_word(created)}, skipped {skipped} existing.",
    )


def _slots_word(count: int) -> str:
    return "slot" if count == 1 else "slots"
