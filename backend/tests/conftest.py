from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot",
)
SYNC_DB_URL = TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)


@pytest.fixture(scope="session")
def db_engine():  # type: ignore[no-untyped-def]
    engine = create_engine(SYNC_DB_URL)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def _reset_rate_limiters():  # type: ignore[no-untyped-def]
    from backend.rate_limit import reset_all

    reset_all()


@pytest.fixture(autouse=True)
def _migrate_fresh(db_engine):  # type: ignore[no-untyped-def]
    with db_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=str(BACKEND_DIR),
        env={**os.environ, "DATABASE_URL": TEST_DB_URL},
        capture_output=True,
    )


@pytest.fixture(autouse=True)
def _no_real_ai_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # tests never read the real key and models from .env; they inject fake-server settings
    monkeypatch.setattr("backend.app.load_ai_settings", lambda: None)
