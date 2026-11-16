from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

OPENAI_BASE_URL = "https://api.openai.com/v1"

OutputTokenParam = Literal["max_completion_tokens", "max_tokens"]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]
RetrievalMode = Literal["hybrid", "dense", "sparse"]
RerankProvider = Literal["none", "target"]


class Role(StrEnum):
    chat = "chat"
    router = "router"
    rewrite = "rewrite"
    embedding = "embedding"
    rerank = "rerank"
    judge = "judge"


class RoleNotConfigured(ValueError):
    pass


class RoleConfig(BaseModel):
    role: Role
    base_url: str
    api_key: SecretStr
    model: str
    output_token_param: OutputTokenParam
    reasoning_effort: ReasoningEffort | None
    timeout_s: float
    max_retries: int


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    openai_api_key: SecretStr | None = None

    ai_chat_base_url: str = OPENAI_BASE_URL
    ai_chat_api_key: SecretStr | None = None
    ai_chat_model: str | None = None
    ai_chat_output_token_param: OutputTokenParam = "max_completion_tokens"
    ai_chat_reasoning_effort: ReasoningEffort | None = None

    ai_router_base_url: str = OPENAI_BASE_URL
    ai_router_api_key: SecretStr | None = None
    ai_router_model: str | None = None
    ai_router_output_token_param: OutputTokenParam = "max_completion_tokens"
    ai_router_reasoning_effort: ReasoningEffort | None = None
    ai_router_max_output_tokens: int = Field(default=512, gt=0)

    ai_rewrite_base_url: str = OPENAI_BASE_URL
    ai_rewrite_api_key: SecretStr | None = None
    ai_rewrite_model: str | None = None
    ai_rewrite_output_token_param: OutputTokenParam = "max_completion_tokens"
    ai_rewrite_reasoning_effort: ReasoningEffort | None = None
    ai_rewrite_max_output_tokens: int = Field(default=1024, gt=0)

    ai_embedding_base_url: str = OPENAI_BASE_URL
    ai_embedding_api_key: SecretStr | None = None
    ai_embedding_model: str | None = None

    ai_rerank_base_url: str = OPENAI_BASE_URL
    ai_rerank_api_key: SecretStr | None = None
    ai_rerank_model: str | None = None

    ai_judge_base_url: str = OPENAI_BASE_URL
    ai_judge_api_key: SecretStr | None = None
    ai_judge_model: str | None = None
    ai_judge_output_token_param: OutputTokenParam = "max_completion_tokens"
    ai_judge_reasoning_effort: ReasoningEffort | None = None

    ai_timeout_s: float = Field(default=60.0, gt=0)
    ai_max_retries: int = Field(default=2, ge=0)

    ai_embedding_dimensions: int = Field(gt=0)
    ai_embedding_query_prefix: str = ""
    ai_embedding_doc_prefix: str = ""

    ai_query_count: int = Field(default=3, ge=1, le=5)
    ai_retrieval_mode: RetrievalMode = "hybrid"
    ai_prefetch_k: int = Field(default=20, gt=0)
    ai_fused_k: int = Field(default=30, gt=0)
    ai_context_k: int = Field(default=5, gt=0)
    ai_rerank_provider: RerankProvider = "none"
    ai_rerank_min_score: float | None = None
    ai_chunk_max_tokens: int = Field(default=512, gt=0)
    ai_embed_batch: int = Field(default=64, gt=0)
    ai_max_tool_rounds: int = Field(default=4, gt=0)
    ai_chat_max_output_tokens: int = Field(default=800, gt=0)
    ai_router_history_rows: int = Field(default=6, gt=0)
    ingest_timeout_s: float = Field(default=600.0, gt=0)

    qdrant_url: str

    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str | None = None

    def role(self, role: Role) -> RoleConfig:
        prefix = f"ai_{role.value}_"
        model: str | None = getattr(self, f"{prefix}model")
        if not model:
            raise RoleNotConfigured(f"AI_{role.value.upper()}_MODEL is not set")
        api_key: SecretStr | None = getattr(self, f"{prefix}api_key") or self.openai_api_key
        if api_key is None:
            raise RoleNotConfigured(f"AI_{role.value.upper()}_API_KEY and OPENAI_API_KEY are both unset")
        output_param: OutputTokenParam = getattr(self, f"{prefix}output_token_param", "max_completion_tokens")
        effort: ReasoningEffort | None = getattr(self, f"{prefix}reasoning_effort", None)
        return RoleConfig(
            role=role,
            base_url=getattr(self, f"{prefix}base_url"),
            api_key=api_key,
            model=model,
            output_token_param=output_param,
            reasoning_effort=effort,
            timeout_s=self.ai_timeout_s,
            max_retries=self.ai_max_retries,
        )
