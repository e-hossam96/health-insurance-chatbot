from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import Settings


def create_engine(settings: Settings) -> tuple[
    AsyncSession,
    async_sessionmaker[AsyncSession],
]:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory  # type: ignore[return-value]
