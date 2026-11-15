import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.auth import purge_expired
from backend.config import Settings
from backend.database import create_engine
from backend.metrics import prometheus_middleware
from backend.routes.admin import router as admin_router
from backend.routes.auth import router as auth_router
from backend.routes.chat import router as chat_router
from backend.routes.locations import router as locations_router
from backend.routes.me import router as me_router
from backend.routes.visits import router as visits_router


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()  # type: ignore[call-arg]

    engine, session_factory = create_engine(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with session_factory() as db:
            await purge_expired(db)
            await db.commit()
        yield
        await engine.dispose()

    application = FastAPI(title="Health Insurance Chatbot", lifespan=lifespan)
    application.state.settings = settings
    application.state.session_factory = session_factory
    application.state.engine = engine

    application.middleware("http")(prometheus_middleware)
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(locations_router)
    application.include_router(me_router)
    application.include_router(chat_router)
    application.include_router(visits_router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/items/{item_id}")
    async def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    return application


if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot"

app = create_app()
