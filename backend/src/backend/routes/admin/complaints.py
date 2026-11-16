from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.deps import CurrentSession, Db, RequireAdmin
from backend.errors import api_error, not_found
from backend.models import Complaint, ComplaintReply, ComplaintStatus
from backend.queries import count_rows

router = APIRouter()


class ReplyCreate(BaseModel):
    body: str = Field(min_length=1)


class ReplyOut(BaseModel):
    id: int
    complaint_id: int
    admin_account_id: int
    body: str


async def _open_complaint(db: Db, complaint_id: int, closed_message: str) -> Complaint:
    complaint = await db.get(Complaint, complaint_id)
    if complaint is None:
        raise not_found("Complaint not found.")
    # E5
    if complaint.status == ComplaintStatus.closed:
        raise api_error("complaint_closed", closed_message, 409)
    return complaint


@router.post("/complaints/{complaint_id}/reply", status_code=201)
async def reply_to_complaint(
    complaint_id: int,
    body: ReplyCreate,
    admin: RequireAdmin,
    session: CurrentSession,
    db: Db,
) -> ReplyOut:
    await _open_complaint(db, complaint_id, "Cannot reply to a closed complaint.")
    # B7: RequireAdmin guarantees the replying account is an admin
    reply = ComplaintReply(complaint_id=complaint_id, admin_account_id=session.account_id, body=body.body)
    db.add(reply)
    await db.flush()
    await db.commit()
    # E4: a reply leaves the complaint status unchanged
    return ReplyOut(id=reply.id, complaint_id=reply.complaint_id, admin_account_id=reply.admin_account_id, body=reply.body)


@router.post("/complaints/{complaint_id}/close")
async def close_complaint(complaint_id: int, admin: RequireAdmin, db: Db) -> dict[str, object]:
    complaint = await _open_complaint(db, complaint_id, "Complaint is already closed.")
    complaint.status = ComplaintStatus.closed
    await db.commit()
    return {"id": complaint.id, "status": complaint.status.value}


@router.get("/complaints")
async def admin_list_complaints(
    admin: RequireAdmin,
    db: Db,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> dict[str, object]:
    query = select(Complaint)
    if status is not None:
        query = query.where(Complaint.status == status)
    total = await count_rows(db, query)

    result = await db.execute(query.order_by(Complaint.created_at.desc()).limit(limit).offset(offset))
    items = [
        {"id": c.id, "visit_id": c.visit_id, "description": c.description, "status": c.status.value}
        for c in result.scalars()
    ]
    return {"items": items, "total": total}
