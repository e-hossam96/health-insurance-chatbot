"""Admin routes placeholder (requires admin role + admin mode)."""

from __future__ import annotations

from fastapi import APIRouter

from backend.deps import Db, RequireAdmin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/kb")
async def list_kb(
    admin: RequireAdmin,
    db: Db,
) -> dict[str, object]:
    return {"items": [], "total": 0}
