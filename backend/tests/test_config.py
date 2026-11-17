import pytest
from pydantic import ValidationError

from backend.config import Settings


def test_database_url_is_built_from_the_postgres_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "app")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss/w:rd")
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    monkeypatch.setenv("POSTGRES_DB", "insurer")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database_url == "postgresql+asyncpg://app:p%40ss%2Fw%3Ard@db.internal:6543/insurer"


def test_defaults_load_with_only_the_postgres_password(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("POSTGRES_USER", "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database_url == "postgresql+asyncpg://chatbot:x@localhost:5432/chatbot"
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.session_lifetime_days == 7
    assert settings.kb_max_upload_bytes == 10 * 1024 * 1024


def test_the_password_never_shows_in_the_settings_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "hunter2secret")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "hunter2secret" not in repr(settings)


def test_missing_required_value_raises_readable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]
    assert "postgres_password" in str(exc_info.value)
