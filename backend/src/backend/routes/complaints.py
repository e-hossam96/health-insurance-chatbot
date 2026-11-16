from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from backend.card_messages import (
    CardAction,
    MessageOut,
    slot_label,
    write_card_action_messages,
)
from backend.deps import CurrentSession, Db, RequireUserMode
from backend.errors import api_error, not_found
from backend.metrics import card_action
from backend.models import Complaint, ComplaintReply, Visit, VisitStatus
from backend.ownership import require_owned_chat_session, require_profile

router = APIRouter(prefix="/me", tags=["complaints"])


class FileComplaintRequest(BaseModel):
    session_id: int
    visit_id: int
    description: str


class ComplaintOut(BaseModel):
    id: int
    visit_id: int
    description: str
    status: str


class FileComplaintResponse(BaseModel):
    complaint: ComplaintOut
    messages: list[MessageOut]


class ReplyItem(BaseModel):
    id: int
    body: str


class ComplaintListItem(BaseModel):
    id: int
    visit_id: int
    description: str
    status: str
    replies: list[ReplyItem]


@router.post("/complaints", status_code=201)
async def file_complaint(
    _: Annotated[None, Depends(card_action("complaint"))],
    body: FileComplaintRequest,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> FileComplaintResponse:
    profile = await require_profile(db, session.account_id)
    await require_owned_chat_session(db, body.session_id, profile.id)

    # E1: only on the member's own completed visit
    visit = (
        await db.execute(select(Visit).where(Visit.id == body.visit_id, Visit.profile_id == profile.id))
    ).scalar_one_or_none()
    if visit is None:
        raise not_found("Visit not found.")
    if visit.status != VisitStatus.completed:
        raise api_error("visit_not_completed", "Complaints can only be filed on completed visits.", 409)

    # E2: one complaint per visit
    existing = await db.execute(select(Complaint).where(Complaint.visit_id == body.visit_id))
    if existing.scalar_one_or_none() is not None:
        raise api_error("complaint_exists", "A complaint already exists for this visit.", 409)

    complaint = Complaint(visit_id=body.visit_id, description=body.description)
    db.add(complaint)
    await db.flush()

    # E6
    messages = await write_card_action_messages(
        db,
        body.session_id,
        CardAction(
            user_text=f"File a complaint about my visit with {await slot_label(db, visit.slot_id)}.",
            tool_name="file_complaint",
            tool_call_id=f"complaint_{complaint.id}",
            arguments={"visit_id": body.visit_id},
            result={"complaint_id": complaint.id, "status": "open"},
            reply="Your complaint has been filed.",
        ),
    )
    complaint_out = ComplaintOut(
        id=complaint.id, visit_id=complaint.visit_id, description=complaint.description, status=complaint.status.value
    )
    await db.commit()
    return FileComplaintResponse(complaint=complaint_out, messages=messages)


@router.get("/complaints")
async def list_my_complaints(
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> list[ComplaintListItem]:
    profile = await require_profile(db, session.account_id)

    complaints = list(
        (
            await db.execute(
                select(Complaint)
                .join(Visit, Complaint.visit_id == Visit.id)
                .where(Visit.profile_id == profile.id)
                .order_by(Complaint.created_at.desc())
            )
        ).scalars()
    )
    replies = await db.execute(
        select(ComplaintReply)
        .where(ComplaintReply.complaint_id.in_([c.id for c in complaints]))
        .order_by(ComplaintReply.created_at)
    )
    replies_by_complaint: dict[int, list[ReplyItem]] = {}
    for reply in replies.scalars():
        replies_by_complaint.setdefault(reply.complaint_id, []).append(ReplyItem(id=reply.id, body=reply.body))
    return [
        ComplaintListItem(
            id=c.id,
            visit_id=c.visit_id,
            description=c.description,
            status=c.status.value,
            replies=replies_by_complaint.get(c.id, []),
        )
        for c in complaints
    ]
