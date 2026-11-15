from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


def _insert_account(conn: object, username: str = "alice") -> int:
    result = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO account (username, password_hash, role) "
            "VALUES (:u, 'hash', 'user') RETURNING id"
        ),
        {"u": username},
    )
    return result.scalar_one()  # type: ignore[union-attr]


def _insert_location(conn: object, name: str = "Cairo") -> int:
    result = conn.execute(  # type: ignore[union-attr]
        text("INSERT INTO location (name) VALUES (:n) RETURNING id"),
        {"n": name},
    )
    return result.scalar_one()  # type: ignore[union-attr]


def _insert_profile(conn: object, account_id: int, location_id: int) -> int:
    result = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO profile (account_id, name, location_id) "
            "VALUES (:a, 'Alice', :l) RETURNING id"
        ),
        {"a": account_id, "l": location_id},
    )
    return result.scalar_one()  # type: ignore[union-attr]


def _insert_specialty(conn: object, name: str = "Cardiology") -> int:
    result = conn.execute(  # type: ignore[union-attr]
        text("INSERT INTO specialty (name) VALUES (:n) RETURNING id"),
        {"n": name},
    )
    return result.scalar_one()  # type: ignore[union-attr]


def _insert_clinic(conn: object, location_id: int, name: str = "Clinic A") -> int:
    result = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO clinic (location_id, name) "
            "VALUES (:l, :n) RETURNING id"
        ),
        {"l": location_id, "n": name},
    )
    return result.scalar_one()  # type: ignore[union-attr]


def _insert_clinic_specialty(
    conn: object, clinic_id: int, specialty_id: int
) -> int:
    result = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO clinic_specialty (clinic_id, specialty_id) "
            "VALUES (:c, :s) RETURNING id"
        ),
        {"c": clinic_id, "s": specialty_id},
    )
    return result.scalar_one()  # type: ignore[union-attr]


def _insert_doctor(conn: object, clinic_specialty_id: int, name: str = "Dr X") -> int:
    result = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO doctor (clinic_specialty_id, name) "
            "VALUES (:cs, :n) RETURNING id"
        ),
        {"cs": clinic_specialty_id, "n": name},
    )
    return result.scalar_one()  # type: ignore[union-attr]


def _insert_slot(
    conn: object, doctor_id: int, start_at: str, status: str = "available"
) -> int:
    result = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO slot (doctor_id, start_at, status) "
            "VALUES (:d, :s, :st) RETURNING id"
        ),
        {"d": doctor_id, "s": start_at, "st": status},
    )
    return result.scalar_one()  # type: ignore[union-attr]


def _insert_visit(
    conn: object, profile_id: int, slot_id: int, status: str = "scheduled"
) -> int:
    result = conn.execute(  # type: ignore[union-attr]
        text(
            "INSERT INTO visit (profile_id, slot_id, status) "
            "VALUES (:p, :s, :st) RETURNING id"
        ),
        {"p": profile_id, "s": slot_id, "st": status},
    )
    return result.scalar_one()  # type: ignore[union-attr]


def _setup_doctor(conn: object) -> tuple[int, int, int]:
    loc_id = _insert_location(conn)
    acct_id = _insert_account(conn)
    profile_id = _insert_profile(conn, acct_id, loc_id)
    spec_id = _insert_specialty(conn)
    clinic_id = _insert_clinic(conn, loc_id)
    cs_id = _insert_clinic_specialty(conn, clinic_id, spec_id)
    doctor_id = _insert_doctor(conn, cs_id)
    return profile_id, doctor_id, loc_id


# --- A1: slot.start_at must be on the hour ---


def test_A1_slot_on_the_hour_rejected(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        _, doctor_id, _ = _setup_doctor(conn)
        with pytest.raises(IntegrityError, match="ck_slot_on_the_hour"):
            _insert_slot(conn, doctor_id, "2026-12-01 10:30:00+00")
        conn.rollback()


def test_A1_slot_on_the_hour_accepted(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        _, doctor_id, _ = _setup_doctor(conn)
        slot_id = _insert_slot(conn, doctor_id, "2026-12-01 10:00:00+00")
        assert slot_id > 0
        conn.rollback()


# --- A2: one active visit per slot ---


def test_A2_two_active_visits_rejected(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        profile_id, doctor_id, loc_id = _setup_doctor(conn)
        slot_id = _insert_slot(conn, doctor_id, "2026-12-01 10:00:00+00")
        _insert_visit(conn, profile_id, slot_id, "scheduled")

        acct2 = _insert_account(conn, "bob")
        profile2 = _insert_profile(conn, acct2, loc_id)
        with pytest.raises(IntegrityError, match="visit_active_slot_uniq"):
            _insert_visit(conn, profile2, slot_id, "scheduled")
        conn.rollback()


def test_A2_cancelled_visit_frees_slot(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        profile_id, doctor_id, loc_id = _setup_doctor(conn)
        slot_id = _insert_slot(conn, doctor_id, "2026-12-01 10:00:00+00")
        visit_id = _insert_visit(conn, profile_id, slot_id, "scheduled")
        conn.execute(  # type: ignore[union-attr]
            text("UPDATE visit SET status = 'cancelled' WHERE id = :v"),
            {"v": visit_id},
        )
        acct2 = _insert_account(conn, "bob")
        profile2 = _insert_profile(conn, acct2, loc_id)
        visit2 = _insert_visit(conn, profile2, slot_id, "scheduled")
        assert visit2 > 0
        conn.rollback()


# --- A3: file_size_bytes > 0 ---


def test_A3_file_size_zero_rejected(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        acct_id = _insert_account(conn)
        with pytest.raises(IntegrityError, match="ck_kb_document_file_size"):
            conn.execute(  # type: ignore[union-attr]
                text(
                    "INSERT INTO kb_document "
                    "(filename, file_type, file_size_bytes, storage_path, content_hash, uploaded_by) "
                    "VALUES ('a.pdf', 'pdf', 0, '/tmp/a', 'abc123', :u)"
                ),
                {"u": acct_id},
            )
        conn.rollback()


def test_A3_file_size_negative_rejected(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        acct_id = _insert_account(conn)
        with pytest.raises(IntegrityError, match="ck_kb_document_file_size"):
            conn.execute(  # type: ignore[union-attr]
                text(
                    "INSERT INTO kb_document "
                    "(filename, file_type, file_size_bytes, storage_path, content_hash, uploaded_by) "
                    "VALUES ('a.pdf', 'pdf', -1, '/tmp/a', 'abc123', :u)"
                ),
                {"u": acct_id},
            )
        conn.rollback()


# --- A4: case-insensitive unique ---


def test_A4_location_case_insensitive(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        _insert_location(conn, "Cairo")
        with pytest.raises(IntegrityError):
            _insert_location(conn, "cairo")
        conn.rollback()


def test_A4_specialty_case_insensitive(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        _insert_specialty(conn, "Cardiology")
        with pytest.raises(IntegrityError):
            _insert_specialty(conn, "cardiology")
        conn.rollback()


def test_A4_username_case_insensitive(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        _insert_account(conn, "Alice")
        with pytest.raises(IntegrityError):
            _insert_account(conn, "alice")
        conn.rollback()


# --- A5: cascade and restrict ---


def test_A5_cascade_location_deletes_clinic(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        loc_id = _insert_location(conn)
        _insert_clinic(conn, loc_id)
        conn.execute(text("DELETE FROM location WHERE id = :l"), {"l": loc_id})  # type: ignore[union-attr]
        count = conn.execute(text("SELECT count(*) FROM clinic")).scalar()  # type: ignore[union-attr]
        assert count == 0
        conn.rollback()


def test_A5_cascade_clinic_deletes_clinic_specialty(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        loc_id = _insert_location(conn)
        clinic_id = _insert_clinic(conn, loc_id)
        spec_id = _insert_specialty(conn)
        _insert_clinic_specialty(conn, clinic_id, spec_id)
        conn.execute(text("DELETE FROM clinic WHERE id = :c"), {"c": clinic_id})  # type: ignore[union-attr]
        count = conn.execute(text("SELECT count(*) FROM clinic_specialty")).scalar()  # type: ignore[union-attr]
        assert count == 0
        conn.rollback()


def test_A5_cascade_clinic_specialty_deletes_doctor(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        loc_id = _insert_location(conn)
        clinic_id = _insert_clinic(conn, loc_id)
        spec_id = _insert_specialty(conn)
        cs_id = _insert_clinic_specialty(conn, clinic_id, spec_id)
        _insert_doctor(conn, cs_id)
        conn.execute(text("DELETE FROM clinic_specialty WHERE id = :cs"), {"cs": cs_id})  # type: ignore[union-attr]
        count = conn.execute(text("SELECT count(*) FROM doctor")).scalar()  # type: ignore[union-attr]
        assert count == 0
        conn.rollback()


def test_A5_cascade_doctor_deletes_slot(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        _, doctor_id, _ = _setup_doctor(conn)
        _insert_slot(conn, doctor_id, "2026-12-01 10:00:00+00")
        conn.execute(text("DELETE FROM doctor WHERE id = :d"), {"d": doctor_id})  # type: ignore[union-attr]
        count = conn.execute(text("SELECT count(*) FROM slot")).scalar()  # type: ignore[union-attr]
        assert count == 0
        conn.rollback()


def test_A5_cascade_complaint_deletes_reply(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        profile_id, doctor_id, _ = _setup_doctor(conn)
        slot_id = _insert_slot(conn, doctor_id, "2026-12-01 10:00:00+00")
        visit_id = _insert_visit(conn, profile_id, slot_id)
        conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO complaint (visit_id, description) "
                "VALUES (:v, 'bad service')"
            ),
            {"v": visit_id},
        )
        complaint_id = conn.execute(text("SELECT id FROM complaint")).scalar()  # type: ignore[union-attr]
        admin_id = _insert_account(conn, "admin1")
        conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO complaint_reply (complaint_id, admin_account_id, body) "
                "VALUES (:c, :a, 'sorry')"
            ),
            {"c": complaint_id, "a": admin_id},
        )
        conn.execute(text("DELETE FROM complaint WHERE id = :c"), {"c": complaint_id})  # type: ignore[union-attr]
        count = conn.execute(text("SELECT count(*) FROM complaint_reply")).scalar()  # type: ignore[union-attr]
        assert count == 0
        conn.rollback()


def test_A5_cascade_chat_session_deletes_messages(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        loc_id = _insert_location(conn)
        acct_id = _insert_account(conn)
        profile_id = _insert_profile(conn, acct_id, loc_id)
        session_id = conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO chat_session (profile_id) "
                "VALUES (:p) RETURNING id"
            ),
            {"p": profile_id},
        ).scalar_one()
        conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO chat_message (session_id, role, content) "
                "VALUES (:s, 'user', 'hello')"
            ),
            {"s": session_id},
        )
        conn.execute(text("DELETE FROM chat_session WHERE id = :s"), {"s": session_id})  # type: ignore[union-attr]
        count = conn.execute(text("SELECT count(*) FROM chat_message")).scalar()  # type: ignore[union-attr]
        assert count == 0
        conn.rollback()


def test_A5_cascade_account_deletes_auth_session(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        acct_id = _insert_account(conn)
        conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO auth_session (id, account_id, active_mode, expires_at) "
                "VALUES ('tok', :a, 'user', '2027-01-01 00:00:00+00')"
            ),
            {"a": acct_id},
        )
        conn.execute(text("DELETE FROM account WHERE id = :a"), {"a": acct_id})  # type: ignore[union-attr]
        count = conn.execute(text("SELECT count(*) FROM auth_session")).scalar()  # type: ignore[union-attr]
        assert count == 0
        conn.rollback()


def test_A5_restrict_visit_slot(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        profile_id, doctor_id, _ = _setup_doctor(conn)
        slot_id = _insert_slot(conn, doctor_id, "2026-12-01 10:00:00+00")
        _insert_visit(conn, profile_id, slot_id)
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM slot WHERE id = :s"), {"s": slot_id})  # type: ignore[union-attr]
        conn.rollback()


def test_A5_restrict_visit_profile(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        profile_id, doctor_id, _ = _setup_doctor(conn)
        slot_id = _insert_slot(conn, doctor_id, "2026-12-01 10:00:00+00")
        _insert_visit(conn, profile_id, slot_id)
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM profile WHERE id = :p"), {"p": profile_id})  # type: ignore[union-attr]
        conn.rollback()


def test_A5_restrict_profile_account(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        loc_id = _insert_location(conn)
        acct_id = _insert_account(conn)
        _insert_profile(conn, acct_id, loc_id)
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM account WHERE id = :a"), {"a": acct_id})  # type: ignore[union-attr]
        conn.rollback()


def test_A5_restrict_profile_location(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        loc_id = _insert_location(conn)
        acct_id = _insert_account(conn)
        _insert_profile(conn, acct_id, loc_id)
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM location WHERE id = :l"), {"l": loc_id})  # type: ignore[union-attr]
        conn.rollback()


def test_A5_restrict_specialty_in_clinic_specialty(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        loc_id = _insert_location(conn)
        clinic_id = _insert_clinic(conn, loc_id)
        spec_id = _insert_specialty(conn)
        _insert_clinic_specialty(conn, clinic_id, spec_id)
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM specialty WHERE id = :s"), {"s": spec_id})  # type: ignore[union-attr]
        conn.rollback()


def test_A5_restrict_kb_document_uploaded_by(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        acct_id = _insert_account(conn)
        conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO kb_document "
                "(filename, file_type, file_size_bytes, storage_path, content_hash, uploaded_by) "
                "VALUES ('a.pdf', 'pdf', 100, '/tmp/a', 'abc123', :u)"
            ),
            {"u": acct_id},
        )
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM account WHERE id = :a"), {"a": acct_id})  # type: ignore[union-attr]
        conn.rollback()


def test_A5_restrict_complaint_reply_admin(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        profile_id, doctor_id, _ = _setup_doctor(conn)
        slot_id = _insert_slot(conn, doctor_id, "2026-12-01 10:00:00+00")
        visit_id = _insert_visit(conn, profile_id, slot_id)
        conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO complaint (visit_id, description) "
                "VALUES (:v, 'bad')"
            ),
            {"v": visit_id},
        )
        complaint_id = conn.execute(text("SELECT id FROM complaint")).scalar()  # type: ignore[union-attr]
        admin_id = _insert_account(conn, "admin1")
        conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO complaint_reply (complaint_id, admin_account_id, body) "
                "VALUES (:c, :a, 'sorry')"
            ),
            {"c": complaint_id, "a": admin_id},
        )
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM account WHERE id = :a"), {"a": admin_id})  # type: ignore[union-attr]
        conn.rollback()


def test_A5_restrict_chat_session_profile(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        loc_id = _insert_location(conn)
        acct_id = _insert_account(conn)
        profile_id = _insert_profile(conn, acct_id, loc_id)
        conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO chat_session (profile_id) VALUES (:p)"
            ),
            {"p": profile_id},
        )
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM profile WHERE id = :p"), {"p": profile_id})  # type: ignore[union-attr]
        conn.rollback()


def test_A5_restrict_complaint_visit(db_engine: Engine) -> None:
    with db_engine.connect() as conn:
        profile_id, doctor_id, _ = _setup_doctor(conn)
        slot_id = _insert_slot(conn, doctor_id, "2026-12-01 10:00:00+00")
        visit_id = _insert_visit(conn, profile_id, slot_id)
        conn.execute(  # type: ignore[union-attr]
            text(
                "INSERT INTO complaint (visit_id, description) VALUES (:v, 'bad')"
            ),
            {"v": visit_id},
        )
        with pytest.raises(IntegrityError):
            conn.execute(text("DELETE FROM visit WHERE id = :v"), {"v": visit_id})  # type: ignore[union-attr]
        conn.rollback()


# --- A6: timestamps are timestamptz ---


def test_A6_timestamps_are_timestamptz(db_engine: Engine) -> None:
    insp = inspect(db_engine)
    tz_columns = {
        "auth_session": ["created_at", "expires_at"],
        "complaint": ["created_at"],
        "complaint_reply": ["created_at"],
        "chat_session": ["created_at", "last_message_at"],
        "kb_document": ["created_at"],
        "slot": ["start_at"],
    }
    for table, columns in tz_columns.items():
        col_map = {c["name"]: c for c in insp.get_columns(table)}
        for col_name in columns:
            col = col_map[col_name]
            assert col["type"].timezone is True, (
                f"{table}.{col_name} should be timestamptz"
            )
