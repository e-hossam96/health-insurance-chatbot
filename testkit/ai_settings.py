from __future__ import annotations

from chatbot_ai.settings import AISettings, Role
from testkit.qdrant import qdrant_url

ROLE_MODELS = {
    "ai_chat_model": "chat-model",
    "ai_router_model": "router-model",
    "ai_rewrite_model": "rewrite-model",
    "ai_embedding_model": "embedding-model",
    "ai_judge_model": "judge-model",
}


def settings_for(base_url: str, **overrides: object) -> AISettings:
    values: dict[str, object] = {
        "openai_api_key": "test-key",
        "ai_embedding_dimensions": 64,
        "ai_max_retries": 0,
        "qdrant_url": qdrant_url(),
        **ROLE_MODELS,
        **{f"ai_{role.value}_base_url": base_url for role in Role},
        **overrides,
    }
    return AISettings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]  # pydantic-settings init kwargs
