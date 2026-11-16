from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import Clock, get_session, wall_clock
from backend.config import Settings
from backend.errors import forbidden, not_authenticated
from backend.models import Account, AccountRole, AuthSession


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
        raise not_authenticated()
    session = await get_session(db, session_id, clock=clock)
    if session is None:
        raise not_authenticated()
    return session


CurrentSession = Annotated[AuthSession, Depends(get_current_session)]


async def get_current_account(db: Db, session: CurrentSession) -> Account:
    account = await db.get(Account, session.account_id)
    if account is None:
        raise not_authenticated()
    return account


CurrentAccount = Annotated[Account, Depends(get_current_account)]


async def require_admin(session: CurrentSession, account: CurrentAccount) -> Account:
    if account.role != AccountRole.admin:
        raise forbidden("Admin role required.")
    if session.active_mode != AccountRole.admin:
        raise forbidden("Admin mode required.")
    return account


async def require_user_mode(session: CurrentSession, account: CurrentAccount) -> Account:
    if session.active_mode != AccountRole.user:
        raise forbidden("User mode required.")
    return account


RequireAdmin = Annotated[Account, Depends(require_admin)]
RequireUserMode = Annotated[Account, Depends(require_user_mode)]
