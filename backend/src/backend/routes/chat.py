from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import Clock
from backend.deps import (
    ClockDep,
    CurrentSession,
    Db,
    RequireUserMode,
    SettingsDep,
    TurnRunnerDep,
)
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
from chatbot_ai.stub import StubError

router = APIRouter(prefix="/me", tags=["chat"])


def _error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": message}},
    )


class ChatRequest(BaseModel):
    session_id: int | None = None
    message: str


@dataclass(frozen=True)
class PreparedTurn:
    session_id: int
    needs_label: bool
    request: TurnRequest


async def prepare_turn(
    body: ChatRequest,
    user: RequireUserMode,
    session: CurrentSession,
    db: Db,
    clock: ClockDep,
    settings: SettingsDep,
) -> PreparedTurn:
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

    retry = chat_minute_limiter.check(user_key, clock=clock)
    if retry is not None:
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "rate_limited", "message": "Too many messages."}},
            headers={"Retry-After": str(retry)},
        )

    if user.role != AccountRole.admin and chat_daily_limiter.check(user_key, clock=clock):
        raise HTTPException(
            status_code=429,
            detail={"error": {"code": "rate_limited", "message": "Daily message limit reached."}},
        )

    # F15: counted when the turn starts, so cancelled and failed turns count too
    chat_minute_limiter.record(user_key, clock=clock)
    if user.role != AccountRole.admin:
        chat_daily_limiter.record(user_key, clock=clock)

    chat_session: ChatSession
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

    history_rows = await _load_history(db, session_id)
    return PreparedTurn(
        session_id=session_id,
        needs_label=needs_label,
        request=TurnRequest(
            history=build_context(history_rows),
            message=body.message,
            profile=ProfileInfo(
                display_name=profile.name,
                location_name="",
                location_id=profile.location_id,
            ),
            needs_label=needs_label,
            session_id=session_id,
        ),
    )


@router.post("/chat", response_class=EventSourceResponse)
async def chat(
    turn: Annotated[PreparedTurn, Depends(prepare_turn)],
    db: Db,
    clock: ClockDep,
    run_turn: TurnRunnerDep,
) -> AsyncIterable[ServerSentEvent]:
    yield ServerSentEvent(event="session", data={"session_id": turn.session_id})

    intent_code: str | None = None
    try:
        async for event in run_turn(turn.request):
            if isinstance(event, Intent):
                intent_code = event.code
                yield ServerSentEvent(event="intent", data={"intent": event.code})
            elif isinstance(event, Token):
                yield ServerSentEvent(event="token", data={"text": event.text})
            elif isinstance(event, Cards):
                yield ServerSentEvent(event="cards", data={"type": event.type, "items": event.items})
            elif isinstance(event, Done):
                await _store_turn(db, turn.session_id, event, clock, intent_code, turn.needs_label)
                yield ServerSentEvent(event="done", data={})
    except StubError:
        yield ServerSentEvent(
            event="error", data={"code": "turn_error", "message": "Something went wrong."}
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
