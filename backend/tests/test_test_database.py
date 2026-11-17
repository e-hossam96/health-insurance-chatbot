from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url

from backend.config import get_settings


def test_the_suite_runs_on_its_own_database_never_the_dev_one(db_engine: Engine) -> None:
    database = make_url(get_settings().database_url).database
    assert database is not None and database.endswith("_test")
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT current_database()")).scalar() == database


def test_each_test_starts_with_empty_tables_and_the_schema_at_head(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM account")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 1
