from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from backend.deps import Db, RequireAdmin
from backend.errors import api_error, not_found
from backend.models import Slot, Visit, VisitStatus
from backend.queries import count_rows

router = APIRouter()


class VisitStatusOut(BaseModel):
    id: int
    status: str


@router.post("/visits/{visit_id}/complete")
async def complete_visit(visit_id: int, admin: RequireAdmin, db: Db) -> VisitStatusOut:
    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise not_found("Visit not found.")
    # D3
    if visit.status != VisitStatus.scheduled:
        raise api_error("invalid_transition", f"Cannot complete a visit with status '{visit.status.value}'.", 409)
    visit.status = VisitStatus.completed
    await db.commit()
    return VisitStatusOut(id=visit.id, status=visit.status.value)


@router.get("/visits")
async def admin_list_visits(
    admin: RequireAdmin,
    db: Db,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> dict[str, object]:
    query = select(Visit)
    if status is not None:
        query = query.where(Visit.status == status)
    total = await count_rows(db, query)

    result = await db.execute(
        query.join(Slot, Visit.slot_id == Slot.id).order_by(Slot.start_at.desc()).limit(limit).offset(offset)
    )
    items = [
        {"id": v.id, "profile_id": v.profile_id, "slot_id": v.slot_id, "status": v.status.value}
        for v in result.scalars()
    ]
    return {"items": items, "total": total}
