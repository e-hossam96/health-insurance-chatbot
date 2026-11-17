from __future__ import annotations

import argparse
import calendar
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine, text

from backend.config import get_settings

SLOT_START_HOUR = 9
SLOT_END_HOUR = 16

LOCATIONS = ["Cairo", "Alexandria", "Giza"]

SPECIALTIES = ["Cardiology", "Dermatology", "Orthopedics", "Pediatrics", "Ophthalmology"]

CLINICS: list[dict[str, str | list[str]]] = [
    {"name": "Nile Heart Center", "location": "Cairo", "specialties": ["Cardiology", "Pediatrics"]},
    {"name": "Delta Skin Clinic", "location": "Alexandria", "specialties": ["Dermatology"]},
    {"name": "Pyramid Ortho", "location": "Giza", "specialties": ["Orthopedics"]},
    {"name": "Cairo Family Clinic", "location": "Cairo", "specialties": ["Pediatrics", "Ophthalmology"]},
    {"name": "Alex General", "location": "Alexandria", "specialties": ["Cardiology", "Dermatology", "Ophthalmology"]},
]

DOCTORS: list[dict[str, str]] = [
    {"name": "Dr. Ahmed Hassan", "clinic": "Nile Heart Center", "specialty": "Cardiology"},
    {"name": "Dr. Fatma Ali", "clinic": "Nile Heart Center", "specialty": "Pediatrics"},
    {"name": "Dr. Omar Said", "clinic": "Delta Skin Clinic", "specialty": "Dermatology"},
    {"name": "Dr. Nour Ibrahim", "clinic": "Pyramid Ortho", "specialty": "Orthopedics"},
    {"name": "Dr. Layla Mahmoud", "clinic": "Cairo Family Clinic", "specialty": "Pediatrics"},
    {"name": "Dr. Karim Youssef", "clinic": "Cairo Family Clinic", "specialty": "Ophthalmology"},
    {"name": "Dr. Sara Helmy", "clinic": "Alex General", "specialty": "Cardiology"},
    {"name": "Dr. Mostafa Adel", "clinic": "Alex General", "specialty": "Dermatology"},
]

SAMPLE_USERS: list[dict[str, str]] = [
    {"username": "user1", "password": "userpass1", "name": "Mohamed Samir", "location": "Cairo"},
    {"username": "user2", "password": "userpass2", "name": "Hana Refaat", "location": "Alexandria"},
]


def _sync_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return url


def _upsert_location(conn: object, name: str) -> int:
    row = conn.execute(  # type: ignore[union-attr]
        text("SELECT id FROM location WHERE lower(name) = lower(:n)"), {"n": name}
    ).fetchone()
    if row is not None:
        return row[0]  # type: ignore[no-any-return]
    return conn.execute(  # type: ignore[union-attr, no-any-return]
        text("INSERT INTO location (name) VALUES (:n) RETURNING id"), {"n": name}
    ).scalar_one()


def _upsert_specialty(conn: object, name: str) -> int:
    row = conn.execute(  # type: ignore[union-attr]
        text("SELECT id FROM specialty WHERE lower(name) = lower(:n)"), {"n": name}
    ).fetchone()
    if row is not None:
        return row[0]  # type: ignore[no-any-return]
    return conn.execute(  # type: ignore[union-attr, no-any-return]
        text("INSERT INTO specialty (name) VALUES (:n) RETURNING id"), {"n": name}
    ).scalar_one()


def _upsert_clinic(conn: object, name: str, location_id: int) -> int:
    row = conn.execute(  # type: ignore[union-attr]
        text("SELECT id FROM clinic WHERE lower(name) = lower(:n) AND location_id = :l"),
        {"n": name, "l": location_id},
    ).fetchone()
    if row is not None:
        return row[0]  # type: ignore[no-any-return]
    return conn.execute(  # type: ignore[union-attr, no-any-return]
        text("INSERT INTO clinic (name, location_id) VALUES (:n, :l) RETURNING id"),
        {"n": name, "l": location_id},
    ).scalar_one()


def _upsert_clinic_specialty(conn: object, clinic_id: int, specialty_id: int) -> int:
    row = conn.execute(  # type: ignore[union-attr]
        text(
            "SELECT id FROM clinic_specialty "
            "WHERE clinic_id = :c AND specialty_id = :s"
        ),
        {"c": clinic_id, "s": specialty_id},
    ).fetchone()
    if row is not None:
        return row[0]  # type: ignore[no-any-return]
    return conn.execute(  # type: ignore[union-attr, no-any-return]
        text(
            "INSERT INTO clinic_specialty (clinic_id, specialty_id) "
            "VALUES (:c, :s) RETURNING id"
        ),
        {"c": clinic_id, "s": specialty_id},
    ).scalar_one()


def _upsert_doctor(conn: object, name: str, clinic_specialty_id: int) -> int:
    row = conn.execute(  # type: ignore[union-attr]
        text(
            "SELECT id FROM doctor WHERE lower(name) = lower(:n) "
            "AND clinic_specialty_id = :cs"
        ),
        {"n": name, "cs": clinic_specialty_id},
    ).fetchone()
    if row is not None:
        return row[0]  # type: ignore[no-any-return]
    return conn.execute(  # type: ignore[union-attr, no-any-return]
        text(
            "INSERT INTO doctor (name, clinic_specialty_id) "
            "VALUES (:n, :cs) RETURNING id"
        ),
        {"n": name, "cs": clinic_specialty_id},
    ).scalar_one()


def _autofill_slots(conn: object, doctor_id: int, now: datetime) -> int:
    today = now.date()
    last_day = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
    created = 0
    current = today
    while current <= last_day:
        for hour in range(SLOT_START_HOUR, SLOT_END_HOUR + 1):
            slot_dt = datetime(current.year, current.month, current.day, hour, 0, tzinfo=UTC)
            if slot_dt < now:
                continue
            result = conn.execute(  # type: ignore[union-attr]
                text(
                    "INSERT INTO slot (doctor_id, start_at) VALUES (:d, :s) "
                    "ON CONFLICT (doctor_id, start_at) DO NOTHING"
                ),
                {"d": doctor_id, "s": slot_dt},
            )
            created += result.rowcount
        current += timedelta(days=1)
    return created


def seed(database_url: str) -> dict[str, int]:
    from argon2 import PasswordHasher

    ph = PasswordHasher()
    engine = create_engine(_sync_url(database_url))
    counts: dict[str, int] = {
        "locations": 0,
        "specialties": 0,
        "clinics": 0,
        "clinic_specialties": 0,
        "doctors": 0,
        "users": 0,
        "slots": 0,
    }

    now = datetime.now(UTC)

    with engine.begin() as conn:
        location_ids: dict[str, int] = {}
        for loc_name in LOCATIONS:
            location_ids[loc_name] = _upsert_location(conn, loc_name)
            counts["locations"] += 1

        specialty_ids: dict[str, int] = {}
        for spec_name in SPECIALTIES:
            specialty_ids[spec_name] = _upsert_specialty(conn, spec_name)
            counts["specialties"] += 1

        clinic_ids: dict[str, int] = {}
        cs_map: dict[tuple[str, str], int] = {}
        for clinic_def in CLINICS:
            clinic_name = str(clinic_def["name"])
            loc_name = str(clinic_def["location"])
            clinic_id = _upsert_clinic(conn, clinic_name, location_ids[loc_name])
            clinic_ids[clinic_name] = clinic_id
            counts["clinics"] += 1

            for spec_name in clinic_def["specialties"]:  # type: ignore[union-attr]
                spec_name_str = str(spec_name)
                cs_id = _upsert_clinic_specialty(conn, clinic_id, specialty_ids[spec_name_str])
                cs_map[(clinic_name, spec_name_str)] = cs_id
                counts["clinic_specialties"] += 1

        doctor_ids: list[int] = []
        for doc_def in DOCTORS:
            cs_id = cs_map[(doc_def["clinic"], doc_def["specialty"])]
            doctor_id = _upsert_doctor(conn, doc_def["name"], cs_id)
            doctor_ids.append(doctor_id)
            counts["doctors"] += 1

        for user_def in SAMPLE_USERS:
            existing = conn.execute(
                text("SELECT id FROM account WHERE lower(username) = lower(:u)"),
                {"u": user_def["username"]},
            ).fetchone()
            if existing is None:
                password_hash = ph.hash(user_def["password"])
                acct_id: int = conn.execute(
                    text(
                        "INSERT INTO account (username, password_hash, role) "
                        "VALUES (:u, :h, 'user') RETURNING id"
                    ),
                    {"u": user_def["username"], "h": password_hash},
                ).scalar_one()
                conn.execute(
                    text(
                        "INSERT INTO profile (account_id, name, location_id) "
                        "VALUES (:a, :n, :l)"
                    ),
                    {"a": acct_id, "n": user_def["name"], "l": location_ids[user_def["location"]]},
                )
            counts["users"] += 1

        for doctor_id in doctor_ids:
            counts["slots"] += _autofill_slots(conn, doctor_id, now)

    engine.dispose()
    return counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed the database with demo data")
    parser.parse_args(argv)

    counts = seed(database_url=get_settings().database_url)

    print(f"Seed complete: {counts}")


if __name__ == "__main__":
    main()
