from __future__ import annotations

import os

from sqlalchemy import create_engine, text

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot",
)


def _sync_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return url


def test_seed_idempotent(_clean_database: None) -> None:
    from scripts.seed import seed

    counts1 = seed(TEST_DB_URL)
    assert counts1["locations"] > 0
    assert counts1["doctors"] > 0

    counts2 = seed(TEST_DB_URL)
    assert counts2["locations"] == counts1["locations"]
    assert counts2["doctors"] == counts1["doctors"]
    assert counts2["slots"] == 0


def test_seed_slots_on_the_hour(_clean_database: None) -> None:
    from scripts.seed import seed

    seed(TEST_DB_URL)
    engine = create_engine(_sync_url(TEST_DB_URL))
    with engine.connect() as conn:
        bad = conn.execute(
            text(
                "SELECT count(*) FROM slot "
                "WHERE extract(minute FROM start_at AT TIME ZONE 'UTC') != 0 "
                "OR extract(second FROM start_at AT TIME ZONE 'UTC') != 0"
            )
        ).scalar_one()
        assert bad == 0


def test_seed_slots_within_working_hours(_clean_database: None) -> None:
    from scripts.seed import seed

    seed(TEST_DB_URL)
    engine = create_engine(_sync_url(TEST_DB_URL))
    with engine.connect() as conn:
        bad = conn.execute(
            text(
                "SELECT count(*) FROM slot "
                "WHERE extract(hour FROM start_at AT TIME ZONE 'UTC') < 9 "
                "OR extract(hour FROM start_at AT TIME ZONE 'UTC') > 16"
            )
        ).scalar_one()
        assert bad == 0
    engine.dispose()
