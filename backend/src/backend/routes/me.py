"""User routes placeholder (requires user mode)."""

from __future__ import annotations

from fastapi import APIRouter

from backend.deps import Db, RequireUserMode

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/sessions")
async def list_sessions(
    user: RequireUserMode,
    db: Db,
) -> dict[str, object]:
    return {"items": []}
