from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        description="PostgreSQL connection URL (asyncpg)",
    )
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant server URL",
    )
    session_lifetime_days: int = Field(
        default=7,
        description="Session cookie lifetime in days",
    )
    kb_max_upload_bytes: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum upload size for KB documents",
    )
    kb_storage_dir: str = Field(
        default="./data/kb",
        description="Directory on the local KB volume that holds the uploaded originals",
    )
    rate_limit_messages_per_minute: int = Field(
        default=6,
        description="Max messages per minute per user",
    )
    rate_limit_messages_per_day: int = Field(
        default=100,
        description="Max messages per day per user (admins exempt)",
    )
    rate_limit_message_max_chars: int = Field(
        default=1000,
        description="Max characters per message",
    )
    langfuse_secret_key: str = Field(
        default="",
        description="Langfuse secret key (tracing disabled if empty)",
    )
    langfuse_public_key: str = Field(
        default="",
        description="Langfuse public key",
    )
    langfuse_host: str = Field(
        default="",
        description="Langfuse host URL",
    )


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
