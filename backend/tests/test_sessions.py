from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.auth import (
    create_session,
    delete_session,
    get_session,
    purge_expired,
)
from backend.config import get_settings
from backend.models import Account, AccountRole, AuthSession

TEST_DB_URL = get_settings().database_url


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        self._now += timedelta(**kwargs)


@pytest.fixture()
async def async_db(
    _clean_database: None,
) -> AsyncSession:
    engine = create_async_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session  # type: ignore[misc]
    await engine.dispose()


async def _make_account(db: AsyncSession, username: str = "alice") -> Account:
    acct = Account(
        username=username,
        password_hash="fake_hash",
        role=AccountRole.user,
    )
    db.add(acct)
    await db.flush()
    return acct


@pytest.mark.anyio()
async def test_B10_raw_token_never_in_database(async_db: AsyncSession) -> None:
    acct = await _make_account(async_db)
    raw_token = await create_session(async_db, acct, lifetime_days=7)
    await async_db.commit()

    result = await async_db.execute(select(AuthSession))
    sessions = result.scalars().all()
    assert len(sessions) == 1
    assert sessions[0].id != raw_token
    expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    assert sessions[0].id == expected_hash


@pytest.mark.anyio()
async def test_B12_expired_session_rejected(async_db: AsyncSession) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    acct = await _make_account(async_db)
    raw_token = await create_session(async_db, acct, lifetime_days=7, clock=clock)
    await async_db.commit()

    clock.advance(days=8)
    session = await get_session(async_db, raw_token, clock=clock)
    assert session is None


@pytest.mark.anyio()
async def test_B10_logout_deletes_row(async_db: AsyncSession) -> None:
    acct = await _make_account(async_db)
    raw_token = await create_session(async_db, acct, lifetime_days=7)
    await async_db.commit()

    await delete_session(async_db, raw_token)
    await async_db.commit()

    result = await async_db.execute(select(AuthSession))
    assert result.scalars().all() == []


@pytest.mark.anyio()
async def test_B10_purge_removes_only_expired(async_db: AsyncSession) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    acct = await _make_account(async_db)

    await create_session(async_db, acct, lifetime_days=1, clock=clock)

    clock.advance(hours=12)
    acct2 = await _make_account(async_db, "bob")
    token_fresh = await create_session(async_db, acct2, lifetime_days=7, clock=clock)
    await async_db.commit()

    clock.advance(hours=13)
    removed = await purge_expired(async_db, clock=clock)
    await async_db.commit()
    assert removed == 1

    session = await get_session(async_db, token_fresh, clock=clock)
    assert session is not None
