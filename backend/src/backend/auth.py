from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Account, AccountRole, AuthSession


class Clock(Protocol):
    def now(self) -> datetime: ...


class _WallClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


wall_clock: Clock = _WallClock()

_ph = PasswordHasher()

SESSION_COOKIE = "session_id"
_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(
    db: AsyncSession,
    account: Account,
    lifetime_days: int,
    clock: Clock | None = None,
) -> str:
    clk = clock or wall_clock
    raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
    token_hash = _hash_token(raw_token)
    now = clk.now()
    session = AuthSession(
        id=token_hash,
        account_id=account.id,
        active_mode=account.role,
        created_at=now,
        expires_at=now + timedelta(days=lifetime_days),
    )
    db.add(session)
    await db.flush()
    return raw_token


async def get_session(
    db: AsyncSession,
    raw_token: str,
    clock: Clock | None = None,
) -> AuthSession | None:
    clk = clock or wall_clock
    token_hash = _hash_token(raw_token)
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.id == token_hash,
            AuthSession.expires_at > clk.now(),
        )
    )
    return result.scalar_one_or_none()


async def delete_session(db: AsyncSession, raw_token: str) -> None:
    token_hash = _hash_token(raw_token)
    await db.execute(delete(AuthSession).where(AuthSession.id == token_hash))


async def purge_expired(db: AsyncSession, clock: Clock | None = None) -> int:
    clk = clock or wall_clock
    result = await db.execute(
        delete(AuthSession).where(AuthSession.expires_at <= clk.now())
    )
    return result.rowcount  # type: ignore[no-any-return, attr-defined]


async def set_active_mode(
    db: AsyncSession, session: AuthSession, mode: AccountRole
) -> None:
    session.active_mode = mode
    await db.flush()
