from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parent.parent

EXPECTED_TABLES = {
    "account",
    "auth_session",
    "location",
    "profile",
    "clinic",
    "specialty",
    "clinic_specialty",
    "doctor",
    "slot",
    "visit",
    "complaint",
    "complaint_reply",
    "chat_session",
    "chat_message",
    "kb_document",
}

EXPECTED_ENUMS = {
    "account_role",
    "slot_status",
    "visit_status",
    "complaint_status",
    "message_role",
    "kb_file_type",
    "kb_document_status",
}


def _get_enum_names(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT typname FROM pg_type "
                "WHERE typcategory = 'E' "
                "ORDER BY typname"
            )
        )
        return {row[0] for row in result}


def _get_fk_info(engine: Engine) -> list[dict[str, object]]:
    insp = inspect(engine)
    fks = []
    for table in insp.get_table_names():
        for fk in insp.get_foreign_keys(table):
            fks.append({"table": table, **fk})
    return fks


def test_migrate_up_finds_all_tables(db_engine: Engine) -> None:
    insp = inspect(db_engine)
    tables = set(insp.get_table_names())
    tables.discard("alembic_version")
    assert tables == EXPECTED_TABLES


def test_migrate_up_finds_all_enums(db_engine: Engine) -> None:
    enums = _get_enum_names(db_engine)
    assert enums == EXPECTED_ENUMS


def test_migrate_up_finds_foreign_keys(db_engine: Engine) -> None:
    fks = _get_fk_info(db_engine)
    fk_set = {(fk["table"], tuple(fk["constrained_columns"])) for fk in fks}
    expected_fks = {
        ("auth_session", ("account_id",)),
        ("profile", ("account_id",)),
        ("profile", ("location_id",)),
        ("clinic", ("location_id",)),
        ("clinic_specialty", ("clinic_id",)),
        ("clinic_specialty", ("specialty_id",)),
        ("doctor", ("clinic_specialty_id",)),
        ("slot", ("doctor_id",)),
        ("visit", ("profile_id",)),
        ("visit", ("slot_id",)),
        ("complaint", ("visit_id",)),
        ("complaint_reply", ("complaint_id",)),
        ("complaint_reply", ("admin_account_id",)),
        ("chat_session", ("profile_id",)),
        ("chat_message", ("session_id",)),
        ("kb_document", ("uploaded_by",)),
    }
    assert fk_set == expected_fks


def test_migrate_down_then_up(db_engine: Engine) -> None:
    subprocess.run(
        ["uv", "run", "alembic", "downgrade", "base"],
        check=True,
        cwd=str(BACKEND_DIR),
        capture_output=True,
    )
    insp = inspect(db_engine)
    tables = set(insp.get_table_names())
    tables.discard("alembic_version")
    assert tables == set()

    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=str(BACKEND_DIR),
        capture_output=True,
    )
    insp = inspect(db_engine)
    tables = set(insp.get_table_names())
    tables.discard("alembic_version")
    assert tables == EXPECTED_TABLES
