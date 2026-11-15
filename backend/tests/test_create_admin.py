"""Tests for step 1.3: create_admin script (B12, B13)."""

from __future__ import annotations

import os

import pytest
from scripts.create_admin import create_admin
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot",
)


def test_B13_creates_account_and_profile(db_engine: Engine) -> None:
    create_admin(TEST_DB_URL, "admin1", "securepass", "Admin One", "Cairo")
    with db_engine.connect() as conn:
        acct = conn.execute(
            text("SELECT id, username, role FROM account WHERE username = 'admin1'")
        ).fetchone()
        assert acct is not None
        assert acct[2] == "admin"

        profile = conn.execute(
            text("SELECT name FROM profile WHERE account_id = :a"),
            {"a": acct[0]},
        ).fetchone()
        assert profile is not None
        assert profile[0] == "Admin One"

        loc = conn.execute(
            text("SELECT name FROM location WHERE lower(name) = 'cairo'")
        ).fetchone()
        assert loc is not None


def test_B12_stored_hash_is_argon2(db_engine: Engine) -> None:
    create_admin(TEST_DB_URL, "admin2", "securepass", "Admin Two", "Cairo")
    with db_engine.connect() as conn:
        row = conn.execute(
            text("SELECT password_hash FROM account WHERE username = 'admin2'")
        ).fetchone()
        assert row is not None
        assert row[0].startswith("$argon2")
        assert "securepass" not in row[0]


def test_B12_short_password_fails(db_engine: Engine) -> None:
    with pytest.raises(ValueError, match="at least 8"):
        create_admin(TEST_DB_URL, "admin3", "short", "Admin Three", "Cairo")


def test_B13_duplicate_username_fails(db_engine: Engine) -> None:
    create_admin(TEST_DB_URL, "admin4", "securepass", "Admin Four", "Cairo")
    with pytest.raises(IntegrityError):
        create_admin(TEST_DB_URL, "admin4", "securepass2", "Admin Four B", "Cairo")
