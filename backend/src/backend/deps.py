"""FastAPI dependencies for database, settings, and auth."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import Clock, get_session, wall_clock
from backend.config import Settings
from backend.models import Account, AuthSession


async def get_db(request: Request) -> AsyncGenerator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


async def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


async def get_clock(request: Request) -> Clock:
    clock: Clock = getattr(request.app.state, "clock", wall_clock)
    return clock


Db = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ClockDep = Annotated[Clock, Depends(get_clock)]


async def get_current_session(
    db: Db,
    clock: ClockDep,
    session_id: str | None = Cookie(default=None),
) -> AuthSession:
    if not session_id:
        raise HTTPException(status_code=401, detail={"error": {"code": "not_authenticated", "message": "Not authenticated."}})
    session = await get_session(db, session_id, clock=clock)
    if session is None:
        raise HTTPException(status_code=401, detail={"error": {"code": "not_authenticated", "message": "Not authenticated."}})
    return session


async def get_current_account(
    db: Db,
    session: Annotated[AuthSession, Depends(get_current_session)],
) -> Account:
    from sqlalchemy import select

    result = await db.execute(
        select(Account).where(Account.id == session.account_id)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=401, detail={"error": {"code": "not_authenticated", "message": "Not authenticated."}})
    return account


CurrentSession = Annotated[AuthSession, Depends(get_current_session)]
CurrentAccount = Annotated[Account, Depends(get_current_account)]
