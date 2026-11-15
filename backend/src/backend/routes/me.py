"""User routes (requires user mode)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.deps import CurrentSession, Db, RequireUserMode
from backend.models import ChatMessage, ChatSession, Location, MessageRole, Profile

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


class SessionOut(BaseModel):
    id: int
    intent: str | None
    created_at: str
    last_message_at: str
    first_user_message: str | None


@router.get("/sessions")
async def list_sessions(
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> list[SessionOut]:
    profile_result = await db.execute(
        select(Profile).where(Profile.account_id == session.account_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        return []

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.profile_id == profile.id)
        .order_by(ChatSession.last_message_at.desc())
    )
    sessions = list(result.scalars())

    items: list[SessionOut] = []
    for cs in sessions:
        # Get first user message for subtitle
        first_msg_result = await db.execute(
            select(ChatMessage.content)
            .where(
                ChatMessage.session_id == cs.id,
                ChatMessage.role == MessageRole.user,
            )
            .order_by(ChatMessage.id)
            .limit(1)
        )
        first_msg = first_msg_result.scalar_one_or_none()
        items.append(SessionOut(
            id=cs.id,
            intent=cs.intent,
            created_at=cs.created_at.isoformat(),
            last_message_at=cs.last_message_at.isoformat(),
            first_user_message=first_msg[:40] if first_msg else None,
        ))
    return items


class MessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str


@router.get("/sessions/{chat_session_id}/messages")
async def list_messages(
    chat_session_id: int,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> list[MessageOut]:
    """F11: only user rows and final assistant rows (content non-empty, no tool_calls)."""
    profile_result = await db.execute(
        select(Profile).where(Profile.account_id == session.account_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Session not found."}},
        )

    cs_result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == chat_session_id,
            ChatSession.profile_id == profile.id,
        )
    )
    if cs_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Session not found."}},
        )

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == chat_session_id)
        .order_by(ChatMessage.id)
    )
    messages = list(result.scalars())

    # F11: user rows + final assistant rows (non-empty content, no tool_calls)
    filtered: list[MessageOut] = []
    for m in messages:
        if m.role == MessageRole.user:
            filtered.append(MessageOut(
                id=m.id, session_id=m.session_id, role="user", content=m.content,
            ))
        elif m.role == MessageRole.assistant and m.content and not m.tool_calls:
            filtered.append(MessageOut(
                id=m.id, session_id=m.session_id, role="assistant", content=m.content,
            ))
    return filtered
