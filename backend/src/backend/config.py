from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_user: str = Field(
        default="chatbot",
        description="PostgreSQL user",
    )
    postgres_password: SecretStr = Field(
        description="PostgreSQL password",
    )
    postgres_host: str = Field(
        default="localhost",
        description="PostgreSQL host",
    )
    postgres_port: int = Field(
        default=5432,
        description="PostgreSQL port",
    )
    postgres_db: str = Field(
        default="chatbot",
        description="PostgreSQL database name",
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

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
