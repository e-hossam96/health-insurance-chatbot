from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on

from backend.deps import CurrentSession, Db, RequireUserMode
from backend.errors import api_error, not_found
from backend.models import ChatMessage, ChatSession, Location, MessageRole, Profile
from backend.ownership import find_owned_chat_session, find_profile

SUBTITLE_MAX_CHARS = 40

router = APIRouter(prefix="/me", tags=["me"])


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1)
    location_id: int


class ProfileOut(BaseModel):
    id: int
    name: str
    location_id: int
    location_name: str


class SessionOut(BaseModel):
    id: int
    intent: str | None
    created_at: str
    last_message_at: str
    first_user_message: str | None


class MessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str


def _is_transcript_row(message: ChatMessage) -> bool:
    # F11: user rows and final assistant rows; tool calls and tool results stay hidden
    if message.role == MessageRole.user:
        return True
    return message.role == MessageRole.assistant and bool(message.content) and not message.tool_calls


@router.post("/profile", status_code=201)
async def create_profile(
    body: ProfileCreate,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> ProfileOut:
    if await find_profile(db, session.account_id) is not None:
        raise api_error("profile_exists", "Profile already exists.", 409)

    location = await db.get(Location, body.location_id)
    if location is None:
        raise not_found("Location not found.")

    profile = Profile(account_id=session.account_id, name=body.name, location_id=body.location_id)
    db.add(profile)
    await db.flush()
    await db.commit()
    return ProfileOut(id=profile.id, name=profile.name, location_id=location.id, location_name=location.name)


@router.get("/sessions")
async def list_sessions(
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> list[SessionOut]:
    profile = await find_profile(db, session.account_id)
    if profile is None:
        return []

    sessions = list(
        (
            await db.execute(
                select(ChatSession)
                .where(ChatSession.profile_id == profile.id)
                .order_by(ChatSession.last_message_at.desc())
            )
        ).scalars()
    )
    first_user_messages = await db.execute(
        select(ChatMessage.session_id, ChatMessage.content)
        .where(ChatMessage.session_id.in_([cs.id for cs in sessions]), ChatMessage.role == MessageRole.user)
        .order_by(ChatMessage.session_id, ChatMessage.id)
        .ext(distinct_on(ChatMessage.session_id))
    )
    subtitles = {session_id: content[:SUBTITLE_MAX_CHARS] for session_id, content in first_user_messages.all()}
    return [
        SessionOut(
            id=cs.id,
            intent=cs.intent,
            created_at=cs.created_at.isoformat(),
            last_message_at=cs.last_message_at.isoformat(),
            first_user_message=subtitles.get(cs.id) or None,
        )
        for cs in sessions
    ]


@router.get("/sessions/{chat_session_id}/messages")
async def list_messages(
    chat_session_id: int,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
) -> list[MessageOut]:
    profile = await find_profile(db, session.account_id)
    if profile is None or await find_owned_chat_session(db, chat_session_id, profile.id) is None:
        raise not_found("Session not found.")

    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == chat_session_id).order_by(ChatMessage.id)
    )
    return [
        MessageOut(id=m.id, session_id=m.session_id, role=m.role.value, content=m.content)
        for m in result.scalars()
        if _is_transcript_row(m)
    ]
