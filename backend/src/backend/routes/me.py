"""User routes (requires user mode)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.deps import CurrentSession, Db, RequireUserMode
from backend.models import Location, Profile

router = APIRouter(prefix="/me", tags=["me"])


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1)
    location_id: int


class ProfileOut(BaseModel):
    id: int
    name: str
    location_id: int
    location_name: str


@router.post("/profile", status_code=201)
async def create_profile(
    body: ProfileCreate,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> ProfileOut:
    existing = await db.execute(
        select(Profile).where(Profile.account_id == session.account_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "profile_exists", "message": "Profile already exists."}},
        )

    loc_result = await db.execute(
        select(Location).where(Location.id == body.location_id)
    )
    location = loc_result.scalar_one_or_none()
    if location is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Location not found."}},
        )

    profile = Profile(
        account_id=session.account_id,
        name=body.name,
        location_id=body.location_id,
    )
    db.add(profile)
    await db.flush()
    await db.commit()

    return ProfileOut(
        id=profile.id,
        name=profile.name,
        location_id=location.id,
        location_name=location.name,
    )


@router.get("/sessions")
async def list_sessions(
    user: RequireUserMode,
    db: Db,
) -> dict[str, object]:
    return {"items": []}
