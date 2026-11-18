from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.deps import CurrentSession, Db, RequireAdmin
from backend.errors import api_error, not_found
from backend.models import (
    Account,
    Clinic,
    Complaint,
    ComplaintReply,
    ComplaintStatus,
    Doctor,
    Location,
    Profile,
    Slot,
    Specialty,
    Visit,
)
from backend.queries import count_rows, join_doctor_catalog

router = APIRouter()


class ReplyCreate(BaseModel):
    body: str = Field(min_length=1)
    close: bool = False


class ReplyOut(BaseModel):
    id: int
    complaint_id: int
    admin_account_id: int
    body: str
    complaint_status: str


class AdminComplaintItem(BaseModel):
    id: int
    visit_id: int
    description: str
    status: str
    created_at: str
    patient_name: str
    reply_count: int


class AdminComplaintList(BaseModel):
    items: list[AdminComplaintItem]
    total: int


class ComplaintVisit(BaseModel):
    id: int
    start_at: str
    doctor_name: str
    specialty: str
    clinic: str
    location: str


class AdminReplyItem(BaseModel):
    id: int
    body: str
    created_at: str
    admin_username: str


class AdminComplaintDetail(BaseModel):
    id: int
    description: str
    status: str
    created_at: str
    patient_name: str
    visit: ComplaintVisit
    replies: list[AdminReplyItem]


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
    complaint = await _open_complaint(db, complaint_id, "Cannot reply to a closed complaint.")
    # B7: RequireAdmin guarantees the replying account is an admin
    reply = ComplaintReply(complaint_id=complaint_id, admin_account_id=session.account_id, body=body.body)
    db.add(reply)
    # E4: only the explicit close flag changes the status
    if body.close:
        complaint.status = ComplaintStatus.closed
    await db.flush()
    await db.commit()
    return ReplyOut(
        id=reply.id,
        complaint_id=reply.complaint_id,
        admin_account_id=reply.admin_account_id,
        body=reply.body,
        complaint_status=complaint.status.value,
    )


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
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: ComplaintStatus | None = None,
) -> AdminComplaintList:
    reply_count = (
        select(func.count(ComplaintReply.id)).where(ComplaintReply.complaint_id == Complaint.id).scalar_subquery()
    )
    query = (
        select(
            Complaint.id,
            Complaint.visit_id,
            Complaint.description,
            Complaint.status,
            Complaint.created_at,
            Profile.name.label("patient_name"),
            reply_count.label("reply_count"),
        )
        .join(Visit, Visit.id == Complaint.visit_id)
        .join(Profile, Profile.id == Visit.profile_id)
    )
    if status is not None:
        query = query.where(Complaint.status == status)
    total = await count_rows(db, query)
    rows = await db.execute(query.order_by(Complaint.created_at.desc(), Complaint.id.desc()).limit(limit).offset(offset))
    return AdminComplaintList(
        items=[
            AdminComplaintItem(
                id=row.id,
                visit_id=row.visit_id,
                description=row.description,
                status=row.status.value,
                created_at=row.created_at.isoformat(),
                patient_name=row.patient_name,
                reply_count=row.reply_count,
            )
            for row in rows
        ],
        total=total,
    )


@router.get("/complaints/{complaint_id}")
async def admin_get_complaint(complaint_id: int, admin: RequireAdmin, db: Db) -> AdminComplaintDetail:
    row = (
        await db.execute(
            join_doctor_catalog(
                select(
                    Complaint.id,
                    Complaint.description,
                    Complaint.status,
                    Complaint.created_at,
                    Profile.name.label("patient_name"),
                    Visit.id.label("visit_id"),
                    Slot.start_at,
                    Doctor.name.label("doctor_name"),
                    Specialty.name.label("specialty"),
                    Clinic.name.label("clinic"),
                    Location.name.label("location"),
                )
                .join(Visit, Visit.id == Complaint.visit_id)
                .join(Profile, Profile.id == Visit.profile_id)
                .join(Slot, Slot.id == Visit.slot_id)
                .join(Doctor, Doctor.id == Slot.doctor_id)
            ).where(Complaint.id == complaint_id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("Complaint not found.")
    replies = await db.execute(
        select(ComplaintReply.id, ComplaintReply.body, ComplaintReply.created_at, Account.username)
        .join(Account, Account.id == ComplaintReply.admin_account_id)
        .where(ComplaintReply.complaint_id == complaint_id)
        .order_by(ComplaintReply.created_at, ComplaintReply.id)
    )
    return AdminComplaintDetail(
        id=row.id,
        description=row.description,
        status=row.status.value,
        created_at=row.created_at.isoformat(),
        patient_name=row.patient_name,
        visit=ComplaintVisit(
            id=row.visit_id,
            start_at=row.start_at.isoformat(),
            doctor_name=row.doctor_name,
            specialty=row.specialty,
            clinic=row.clinic,
            location=row.location,
        ),
        replies=[
            AdminReplyItem(id=r.id, body=r.body, created_at=r.created_at.isoformat(), admin_username=r.username)
            for r in replies
        ],
    )
