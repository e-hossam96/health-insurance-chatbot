from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.errors import api_error, not_found
from backend.models import ChatSession, Profile


async def find_profile(db: AsyncSession, account_id: int) -> Profile | None:
    result = await db.execute(select(Profile).where(Profile.account_id == account_id))
    return result.scalar_one_or_none()


async def require_profile(db: AsyncSession, account_id: int) -> Profile:
    profile = await find_profile(db, account_id)
    if profile is None:
        raise api_error("no_profile", "Create a profile first.", 400)
    return profile


async def find_owned_chat_session(db: AsyncSession, chat_session_id: int, profile_id: int) -> ChatSession | None:
    chat_session = await db.get(ChatSession, chat_session_id)
    if chat_session is None or chat_session.profile_id != profile_id:
        return None
    return chat_session


async def require_owned_chat_session(db: AsyncSession, chat_session_id: int, profile_id: int) -> ChatSession:
    # F2: another member's session looks exactly like a missing one
    chat_session = await find_owned_chat_session(db, chat_session_id, profile_id)
    if chat_session is None:
        raise not_found("Session not found.")
    return chat_session
