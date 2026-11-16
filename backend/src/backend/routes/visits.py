from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update

from backend.card_messages import (
    CardAction,
    MessageOut,
    slot_label,
    write_card_action_messages,
)
from backend.deps import ClockDep, CurrentSession, Db, RequireUserMode
from backend.errors import api_error, not_found
from backend.metrics import card_action
from backend.models import (
    Clinic,
    Doctor,
    Location,
    Slot,
    SlotStatus,
    Specialty,
    Visit,
    VisitStatus,
)
from backend.ownership import require_owned_chat_session, require_profile
from backend.queries import join_doctor_catalog

router = APIRouter(prefix="/me", tags=["visits"])


class VisitOut(BaseModel):
    id: int
    profile_id: int
    slot_id: int
    status: str

    @classmethod
    def from_row(cls, visit: Visit) -> VisitOut:
        return cls(id=visit.id, profile_id=visit.profile_id, slot_id=visit.slot_id, status=visit.status.value)


class BookRequest(BaseModel):
    session_id: int
    slot_id: int


class BookResponse(BaseModel):
    visit: VisitOut
    messages: list[MessageOut]


class CancelRequest(BaseModel):
    session_id: int | None = None


class CancelResponse(BaseModel):
    visit: VisitOut
    messages: list[MessageOut] | None = None


class VisitListItem(BaseModel):
    id: int
    slot_id: int
    status: str
    doctor_name: str
    specialty: str
    clinic: str
    location: str
    start_at: str


@router.post("/visits", status_code=201)
async def book_visit(
    _: Annotated[None, Depends(card_action("book"))],
    body: BookRequest,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
    clock: ClockDep,
) -> BookResponse:
    profile = await require_profile(db, session.account_id)
    await require_owned_chat_session(db, body.session_id, profile.id)

    # D1: the row lock makes the availability check and the booking one atomic step
    slot = (await db.execute(select(Slot).where(Slot.id == body.slot_id).with_for_update())).scalar_one_or_none()
    if slot is None:
        raise not_found("Slot not found.")
    if slot.start_at <= clock.now():
        raise api_error("slot_past", "Cannot book a past slot.", 409)
    if slot.status != SlotStatus.available:
        raise api_error("slot_taken", "This slot was just taken.", 409)

    await db.execute(update(Slot).where(Slot.id == body.slot_id).values(status=SlotStatus.booked))
    visit = Visit(profile_id=profile.id, slot_id=body.slot_id)
    db.add(visit)
    await db.flush()

    # D6
    messages = await write_card_action_messages(
        db,
        body.session_id,
        CardAction(
            user_text=f"Book {await slot_label(db, body.slot_id)}.",
            tool_name="book_visit",
            tool_call_id=f"book_{visit.id}",
            arguments={"slot_id": body.slot_id},
            result={"visit_id": visit.id, "status": "scheduled"},
            reply="Your visit has been booked successfully.",
        ),
    )
    visit_out = VisitOut.from_row(visit)
    await db.commit()
    return BookResponse(visit=visit_out, messages=messages)


@router.post("/visits/{visit_id}/cancel")
async def cancel_visit(
    _: Annotated[None, Depends(card_action("cancel"))],
    visit_id: int,
    body: CancelRequest,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> CancelResponse:
    profile = await require_profile(db, session.account_id)

    visit = (
        await db.execute(select(Visit).where(Visit.id == visit_id, Visit.profile_id == profile.id))
    ).scalar_one_or_none()
    if visit is None:
        raise not_found("Visit not found.")
    if visit.status != VisitStatus.scheduled:
        raise api_error("visit_not_cancellable", "Only scheduled visits can be cancelled.", 409)

    # D2: the visit and its slot change in one transaction
    await db.execute(update(Visit).where(Visit.id == visit_id).values(status=VisitStatus.cancelled))
    await db.execute(update(Slot).where(Slot.id == visit.slot_id).values(status=SlotStatus.available))

    messages: list[MessageOut] | None = None
    # D8: static messages only when the cancel came from a chat card
    if body.session_id is not None:
        await require_owned_chat_session(db, body.session_id, profile.id)
        messages = await write_card_action_messages(
            db,
            body.session_id,
            CardAction(
                user_text=f"Cancel my visit with {await slot_label(db, visit.slot_id)}.",
                tool_name="cancel_visit",
                tool_call_id=f"cancel_{visit_id}",
                arguments={"visit_id": visit_id},
                result={"visit_id": visit_id, "status": "cancelled"},
                reply="Your visit has been cancelled.",
            ),
        )

    visit_out = VisitOut(id=visit.id, profile_id=visit.profile_id, slot_id=visit.slot_id, status=VisitStatus.cancelled.value)
    await db.commit()
    return CancelResponse(visit=visit_out, messages=messages)


@router.get("/visits")
async def list_my_visits(
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> list[VisitListItem]:
    profile = await require_profile(db, session.account_id)

    # D4: doctor, clinic, specialty and location come from joins
    result = await db.execute(
        join_doctor_catalog(
            select(
                Visit.id,
                Visit.slot_id,
                Visit.status,
                Doctor.name.label("doctor_name"),
                Specialty.name.label("specialty"),
                Clinic.name.label("clinic"),
                Location.name.label("location"),
                Slot.start_at,
            )
            .join(Slot, Visit.slot_id == Slot.id)
            .join(Doctor, Slot.doctor_id == Doctor.id)
        )
        .where(Visit.profile_id == profile.id)
        .order_by(Slot.start_at.desc())
    )
    return [
        VisitListItem(
            id=row.id,
            slot_id=row.slot_id,
            status=row.status.value,
            doctor_name=row.doctor_name,
            specialty=row.specialty,
            clinic=row.clinic,
            location=row.location,
            start_at=row.start_at.isoformat(),
        )
        for row in result
    ]
