import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import ValidationError

from backend.auth import purge_expired
from backend.config import Settings
from backend.database import create_engine
from backend.kb_jobs import IngestFunction, KbJobRunner
from backend.metrics import prometheus_middleware
from backend.routes.admin import router as admin_router
from backend.routes.auth import router as auth_router
from backend.routes.chat import router as chat_router
from backend.routes.kb import router as kb_router
from backend.routes.locations import router as locations_router
from backend.routes.me import router as me_router
from backend.routes.visits import router as visits_router
from chatbot_ai.clients import RoleClients
from chatbot_ai.ingest import ensure_collection_once, ingest
from chatbot_ai.settings import AISettings

logger = logging.getLogger(__name__)


def load_ai_settings() -> AISettings | None:
    try:
        return AISettings()  # type: ignore[call-arg]  # values come from the environment
    except ValidationError:
        logger.warning("AI settings are incomplete; KB ingestion and chat models are disabled until they are set")
        return None


def create_app(
    settings: Settings | None = None,
    ai_settings: AISettings | None = None,
    ingest_function: IngestFunction = ingest,
    ai_from_env: bool = True,
) -> FastAPI:
    if settings is None:
        settings = Settings()  # type: ignore[call-arg]
    if ai_settings is None and ai_from_env:
        ai_settings = load_ai_settings()

    engine, session_factory = create_engine(settings)
    kb_runner = KbJobRunner(session_factory, ai_settings, ingest_function)
    role_clients = RoleClients(ai_settings) if ai_settings is not None else None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with session_factory() as db:
            await purge_expired(db)
            await db.commit()
        if ai_settings is not None:
            try:
                await ensure_collection_once(ai_settings)
            except Exception:
                logger.warning("could not prepare the Qdrant collection at startup", exc_info=True)
        await kb_runner.start()
        yield
        await kb_runner.stop()
        if role_clients is not None:
            await role_clients.aclose()
        await engine.dispose()

    application = FastAPI(title="Health Insurance Chatbot", lifespan=lifespan)
    application.state.settings = settings
    application.state.session_factory = session_factory
    application.state.engine = engine
    application.state.kb_runner = kb_runner
    application.state.ai_settings = ai_settings
    application.state.role_clients = role_clients

    application.middleware("http")(prometheus_middleware)
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(locations_router)
    application.include_router(me_router)
    application.include_router(chat_router)
    application.include_router(visits_router)
    application.include_router(kb_router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot"

app = create_app()
