from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, text

from backend.config import get_settings


def _sync_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return url


def create_admin(
    database_url: str,
    username: str,
    password: str,
    name: str,
    location: str,
) -> None:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    from argon2 import PasswordHasher

    ph = PasswordHasher()
    password_hash = ph.hash(password)

    engine = create_engine(_sync_url(database_url))
    with engine.begin() as conn:
        loc_row = conn.execute(
            text("SELECT id FROM location WHERE lower(name) = lower(:n)"),
            {"n": location},
        ).fetchone()
        if loc_row is None:
            loc_id: int = conn.execute(
                text("INSERT INTO location (name) VALUES (:n) RETURNING id"),
                {"n": location},
            ).scalar_one()
        else:
            loc_id = loc_row[0]

        acct_id: int = conn.execute(
            text(
                "INSERT INTO account (username, password_hash, role) "
                "VALUES (:u, :h, 'admin') RETURNING id"
            ),
            {"u": username, "h": password_hash},
        ).scalar_one()

        conn.execute(
            text(
                "INSERT INTO profile (account_id, name, location_id) "
                "VALUES (:a, :n, :l)"
            ),
            {"a": acct_id, "n": name, "l": loc_id},
        )

    engine.dispose()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Create an admin account")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--location", required=True)
    args = parser.parse_args(argv)

    try:
        create_admin(
            database_url=get_settings().database_url,
            username=args.username,
            password=args.password,
            name=args.name,
            location=args.location,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        msg = str(e)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            print("Error: username already exists", file=sys.stderr)
            sys.exit(1)
        raise

    print(f"Admin '{args.username}' created successfully.")


if __name__ == "__main__":
    main()
