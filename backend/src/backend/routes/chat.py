"""Chat endpoint with SSE streaming (F1-F3, F12, F15, F16)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from backend.auth import Clock
from backend.deps import ClockDep, CurrentSession, Db, RequireUserMode, SettingsDep
from backend.models import (
    AccountRole,
    ChatMessage,
    ChatSession,
    MessageRole,
    Profile,
)
from backend.rate_limit import chat_daily_limiter, chat_minute_limiter
from chatbot_ai.context import build_context
from chatbot_ai.interface import (
    Cards,
    Done,
    HistoryRow,
    Intent,
    ProfileInfo,
    Token,
    TurnRequest,
)
from chatbot_ai.stub import StubError, run_stub_turn

router = APIRouter(prefix="/me", tags=["chat"])


def _error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": message}},
    )


class ChatRequest(BaseModel):
    session_id: int | None = None
    message: str


@router.post("/chat")
async def chat(
    body: ChatRequest,
    request: Request,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
    clock: ClockDep,
    settings: SettingsDep,
) -> StreamingResponse:
    if len(body.message) > settings.rate_limit_message_max_chars:
        raise _error(
            "rate_limited",
            f"Message exceeds {settings.rate_limit_message_max_chars} characters.",
            429,
        )

    profile_result = await db.execute(
        select(Profile).where(Profile.account_id == session.account_id)
    )
    profile = profile_result.scalar_one_or_none()
    if profile is None:
        raise _error("no_profile", "Create a profile first.", 400)

    user_key = str(profile.id)

    # F15: per-minute rate limit
    retry = chat_minute_limiter.check(user_key, clock=clock)
    if retry is not None:
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "rate_limited", "message": "Too many messages."}},
            headers={"Retry-After": str(retry)},
        )

    # F15: per-day rate limit (admins exempt)
    if user.role != AccountRole.admin and chat_daily_limiter.check(user_key, clock=clock):
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "rate_limited", "message": "Daily message limit reached."}},
        )

    # Count now so cancelled/failed turns count too (F15)
    chat_minute_limiter.record(user_key, clock=clock)
    if user.role != AccountRole.admin:
        chat_daily_limiter.record(user_key, clock=clock)

    # F1: create session on first message, or validate existing
    chat_session: ChatSession
    needs_label = False
    if body.session_id is None:
        chat_session = ChatSession(profile_id=profile.id)
        db.add(chat_session)
        await db.flush()
        needs_label = True
    else:
        cs_result = await db.execute(
            select(ChatSession).where(ChatSession.id == body.session_id)
        )
        found = cs_result.scalar_one_or_none()
        if found is None or found.profile_id != profile.id:
            raise _error("not_found", "Session not found.", 404)
        chat_session = found
        needs_label = chat_session.intent is None

    session_id = chat_session.id
    await db.commit()

    # F4: load and trim history
    history_rows = await _load_history(db, session_id)
    context = build_context(history_rows)

    turn_req = TurnRequest(
        history=context,
        message=body.message,
        profile=ProfileInfo(
            display_name=profile.name,
            location_name="",
            location_id=profile.location_id,
        ),
        needs_label=needs_label,
        session_id=session_id,
    )

    def _sse(event: str, data: str) -> str:
        return f"event: {event}\ndata: {data}\n\n"

    async def event_generator() -> AsyncGenerator[str]:
        yield _sse("session", json.dumps({"session_id": session_id}))

        intent_code: str | None = None
        try:
            async for event in run_stub_turn(turn_req):
                if await request.is_disconnected():
                    return

                if isinstance(event, Intent):
                    intent_code = event.code
                    yield _sse("intent", json.dumps({"intent": event.code}))
                elif isinstance(event, Token):
                    yield _sse("token", json.dumps({"text": event.text}))
                elif isinstance(event, Cards):
                    yield _sse("cards", json.dumps({"type": event.type, "items": event.items}))
                elif isinstance(event, Done):
                    await _store_turn(db, session_id, event, clock, intent_code, needs_label)
                    yield _sse("done", "{}")

        except StubError:
            yield _sse("error", json.dumps({"code": "turn_error", "message": "Something went wrong."}))
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _load_history(db: AsyncSession, session_id: int) -> list[HistoryRow]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
    )
    return [
        HistoryRow(
            role=m.role.value,
            content=m.content,
            tool_calls=cast(list[dict[str, Any]] | None, m.tool_calls),
            tool_call_id=m.tool_call_id,
            tool_name=m.tool_name,
        )
        for m in result.scalars()
    ]


async def _store_turn(
    db: AsyncSession,
    session_id: int,
    done: Done,
    clock: Clock,
    intent_code: str | None,
    needs_label: bool,
) -> None:
    for row in done.new_rows:
        msg = ChatMessage(
            session_id=session_id,
            role=MessageRole(row.role),
            content=row.content,
            tool_calls=row.tool_calls,
            tool_call_id=row.tool_call_id,
            tool_name=row.tool_name,
        )
        db.add(msg)

    cs_result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    cs = cs_result.scalar_one()
    cs.last_message_at = clock.now()

    if needs_label and intent_code:
        cs.intent = intent_code

    await db.commit()
