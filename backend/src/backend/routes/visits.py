"""Visit routes (booking, cancel, complete, lists)."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update

from backend.deps import ClockDep, CurrentSession, Db, RequireUserMode
from backend.models import (
    ChatMessage,
    ChatSession,
    MessageRole,
    Profile,
    Slot,
    SlotStatus,
    Visit,
)

router = APIRouter(prefix="/me", tags=["visits"])


def _error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": message}},
    )


def _get_profile_id(session: object) -> int:
    return session.account_id  # type: ignore[attr-defined, no-any-return]


# --- Booking (D1, D6, D7, F2) ---


class BookRequest(BaseModel):
    session_id: int
    slot_id: int


class VisitOut(BaseModel):
    id: int
    profile_id: int
    slot_id: int
    status: str


class MessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    tool_calls: object | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


class BookResponse(BaseModel):
    visit: VisitOut
    messages: list[MessageOut]


async def _get_profile_for_session(db: Db, account_id: int) -> Profile:
    result = await db.execute(
        select(Profile).where(Profile.account_id == account_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise _error("no_profile", "Create a profile first.", 400)
    return profile


async def _write_booking_messages(
    db: Db,
    chat_session_id: int,
    slot_id: int,
    visit_id: int,
) -> list[ChatMessage]:
    tool_call_id = f"book_{visit_id}"
    tool_calls_json = [
        {"id": tool_call_id, "type": "function", "function": {"name": "book_visit", "arguments": json.dumps({"slot_id": slot_id})}}
    ]

    m1 = ChatMessage(session_id=chat_session_id, role=MessageRole.user, content=f"Book slot {slot_id}")
    db.add(m1)
    await db.flush()

    m2 = ChatMessage(
        session_id=chat_session_id,
        role=MessageRole.assistant,
        content="",
        tool_calls=tool_calls_json,
    )
    db.add(m2)
    await db.flush()

    m3 = ChatMessage(
        session_id=chat_session_id,
        role=MessageRole.tool,
        content=json.dumps({"visit_id": visit_id, "status": "scheduled"}),
        tool_call_id=tool_call_id,
        tool_name="book_visit",
    )
    db.add(m3)
    await db.flush()

    m4 = ChatMessage(
        session_id=chat_session_id,
        role=MessageRole.assistant,
        content="Your visit has been booked successfully.",
    )
    db.add(m4)
    await db.flush()

    return [m1, m2, m3, m4]


@router.post("/visits", status_code=201)
async def book_visit(
    body: BookRequest,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
    clock: ClockDep,
) -> BookResponse:
    profile = await _get_profile_for_session(db, session.account_id)

    # F2: verify chat session belongs to this profile
    chat_session = await db.get(ChatSession, body.session_id)
    if chat_session is None or chat_session.profile_id != profile.id:
        raise _error("forbidden", "Chat session does not belong to you.", 403)

    # D1: atomic booking with row lock
    now = clock.now()
    slot_result = await db.execute(
        select(Slot)
        .where(Slot.id == body.slot_id)
        .with_for_update()
    )
    slot = slot_result.scalar_one_or_none()
    if slot is None:
        raise _error("not_found", "Slot not found.", 404)
    if slot.start_at <= now:
        raise _error("slot_past", "Cannot book a past slot.", 409)
    if slot.status != SlotStatus.available:
        raise _error("slot_taken", "This slot was just taken.", 409)

    # D1: update slot + insert visit in one transaction
    await db.execute(
        update(Slot).where(Slot.id == body.slot_id).values(status=SlotStatus.booked)
    )
    visit = Visit(profile_id=profile.id, slot_id=body.slot_id)
    db.add(visit)
    await db.flush()

    # D6: write 4 static messages
    messages = await _write_booking_messages(db, body.session_id, body.slot_id, visit.id)

    await db.commit()

    return BookResponse(
        visit=VisitOut(id=visit.id, profile_id=visit.profile_id, slot_id=visit.slot_id, status=visit.status.value),
        messages=[
            MessageOut(
                id=m.id, session_id=m.session_id, role=m.role.value, content=m.content,
                tool_calls=m.tool_calls, tool_call_id=m.tool_call_id, tool_name=m.tool_name,
            )
            for m in messages
        ],
    )
