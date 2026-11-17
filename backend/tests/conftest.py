from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url

from backend.config import get_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DATABASE_DEFAULTS = {
    "POSTGRES_USER": "chatbot",
    "POSTGRES_PASSWORD": "chatbot",
    # 127.0.0.1, not localhost: on Windows a refused ::1 attempt costs about 2 s per new connection
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "chatbot_test",
}
# test modules build Settings at import; never let them fall back to the dev database from .env
for name, default in TEST_DATABASE_DEFAULTS.items():
    os.environ[name] = os.environ.get(f"TEST_{name}", default)

TEST_DB_URL = get_settings().database_url
SYNC_DB_URL = TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)


def _create_test_database() -> None:
    target = make_url(SYNC_DB_URL)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


def _upgrade_to_head() -> None:
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    _create_test_database()
    engine = create_engine(SYNC_DB_URL)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()
    _upgrade_to_head()
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def _data_tables(db_engine: Engine) -> str:
    tables = sorted(set(inspect(db_engine).get_table_names()) - {"alembic_version"})
    return ", ".join(f'"{table}"' for table in tables)


@pytest.fixture(autouse=True)
def _reset_rate_limiters() -> None:
    from backend.rate_limit import reset_all

    reset_all()


@pytest.fixture(autouse=True)
def _clean_database(db_engine: Engine, _data_tables: str) -> None:
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {_data_tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _no_real_ai_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # tests never read the real key and models from .env; they inject fake-server settings
    monkeypatch.setattr("backend.app.load_ai_settings", lambda: None)
