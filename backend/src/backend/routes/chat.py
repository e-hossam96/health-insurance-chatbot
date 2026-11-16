from __future__ import annotations

import logging
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any, cast

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai_ports import make_ports
from backend.auth import Clock
from backend.deps import (
    ClockDep,
    CurrentSession,
    Db,
    RequireUserMode,
    SettingsDep,
)
from backend.models import (
    AccountRole,
    ChatMessage,
    ChatSession,
    Location,
    MessageRole,
    Profile,
)
from backend.rate_limit import chat_daily_limiter, chat_minute_limiter
from chatbot_ai import run_turn
from chatbot_ai.clients import RoleClients
from chatbot_ai.context import build_context, cap_stored_tool_result
from chatbot_ai.interface import (
    Cards,
    Done,
    HistoryRow,
    Intent,
    ProfileInfo,
    Token,
    TurnEvent,
    TurnRequest,
    TurnRunner,
)
from chatbot_ai.settings import AISettings

logger = logging.getLogger(__name__)
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
    profile_id: int
    needs_label: bool
    created_session: bool
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
            "validation_error",
            f"Message exceeds {settings.rate_limit_message_max_chars} characters.",
            422,
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
    location_name = (await db.execute(select(Location.name).where(Location.id == profile.location_id))).scalar_one()
    return PreparedTurn(
        session_id=session_id,
        profile_id=profile.id,
        needs_label=needs_label,
        created_session=body.session_id is None,
        request=TurnRequest(
            history=build_context(history_rows),
            message=body.message,
            profile=ProfileInfo(
                display_name=profile.name,
                location_name=location_name,
                location_id=profile.location_id,
            ),
            needs_label=needs_label,
            session_id=session_id,
        ),
    )


class AINotConfigured(RuntimeError):
    pass


async def _unconfigured_turn(request: TurnRequest) -> AsyncIterator[TurnEvent]:
    raise AINotConfigured("AI settings are missing; set the model roles in the environment")
    yield  # pragma: no cover


def _turn_runner(http_request: Request, db: AsyncSession, clock: Clock, turn: PreparedTurn) -> TurnRunner:
    override: TurnRunner | None = getattr(http_request.app.state, "turn_runner", None)
    if override is not None:
        return override
    ai_settings: AISettings | None = http_request.app.state.ai_settings
    clients: RoleClients | None = http_request.app.state.role_clients
    if ai_settings is None or clients is None:
        return _unconfigured_turn
    ports = make_ports(db, turn.profile_id, turn.request.profile.location_id, clock)

    def runner(request: TurnRequest) -> AsyncIterator[TurnEvent]:
        return run_turn(request, ports, ai_settings, clients)

    return runner


@router.post("/chat", response_class=EventSourceResponse)
async def chat(
    http_request: Request,
    turn: Annotated[PreparedTurn, Depends(prepare_turn)],
    db: Db,
    clock: ClockDep,
) -> AsyncIterable[ServerSentEvent]:
    run_turn_for = _turn_runner(http_request, db, clock, turn)
    yield ServerSentEvent(event="session", data={"session_id": turn.session_id})

    intent_code: str | None = None
    stored = False
    try:
        async for event in run_turn_for(turn.request):
            if isinstance(event, Intent):
                intent_code = event.code
                yield ServerSentEvent(event="intent", data={"intent": event.code})
            elif isinstance(event, Token):
                yield ServerSentEvent(event="token", data={"text": event.text})
            elif isinstance(event, Cards):
                yield ServerSentEvent(event="cards", data={"type": event.type, "items": event.items})
            elif isinstance(event, Done):
                await _store_turn(db, turn.session_id, event, clock, intent_code, turn.needs_label)
                stored = True
                yield ServerSentEvent(event="done", data={})
    except Exception:
        logger.exception("chat turn failed for session %s", turn.session_id)
        await db.rollback()
        yield ServerSentEvent(
            event="error", data={"code": "turn_error", "message": "Something went wrong."}
        )
    finally:
        if turn.created_session and not stored:
            with anyio.CancelScope(shield=True):
                await _drop_empty_session(db, turn.session_id)


async def _drop_empty_session(db: AsyncSession, session_id: int) -> None:
    # F16 and F3: a first turn that stores nothing leaves no session behind
    await db.rollback()
    await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await db.commit()


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
            content=cap_stored_tool_result(row.content) if row.role == "tool" else row.content,
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
