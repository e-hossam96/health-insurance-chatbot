from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from backend.deps import Db
from backend.models import Location

router = APIRouter(tags=["locations"])


class LocationOut(BaseModel):
    id: int
    name: str


@router.get("/locations")
async def list_locations(db: Db) -> list[LocationOut]:
    result = await db.execute(select(Location).order_by(Location.name))
    return [LocationOut(id=loc.id, name=loc.name) for loc in result.scalars()]
