import pytest
from pydantic import ValidationError

from backend.config import Settings


def test_defaults_load_with_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.database_url == "postgresql+asyncpg://x:x@localhost/x"
    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.session_lifetime_days == 7
    assert settings.kb_max_upload_bytes == 10 * 1024 * 1024


def test_missing_required_value_raises_readable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(Settings, "model_config", Settings.model_config.copy())
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]
    error_text = str(exc_info.value)
    assert "database_url" in error_text
