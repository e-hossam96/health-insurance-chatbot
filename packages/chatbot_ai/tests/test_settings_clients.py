from __future__ import annotations

import re
from pathlib import Path

import pytest

from chatbot_ai.clients import RoleClients
from chatbot_ai.settings import AISettings, Role, RoleNotConfigured
from testkit.ai_settings import settings_for
from testkit.fake_openai import FakeOpenAI, text_reply

PACKAGE_SRC = Path(__file__).resolve().parent.parent / "src" / "chatbot_ai"
MODEL_NAME_PATTERN = re.compile(r"gpt-?\d|\bo\d(?:-[a-z]+)?\b|text-embedding-|whisper-|dall-e|claude-|gemini-|llama-?\d|mistral-|qwen", re.IGNORECASE)


def test_I11_each_role_has_its_own_base_url_key_and_model() -> None:
    settings = settings_for(
        "https://default.invalid/v1",
        ai_rewrite_base_url="http://llama.local/v1",
        ai_rewrite_api_key="rewrite-key",
    )
    rewrite = settings.role(Role.rewrite)
    assert (rewrite.base_url, rewrite.api_key.get_secret_value(), rewrite.model) == (
        "http://llama.local/v1",
        "rewrite-key",
        "rewrite-model",
    )
    chat = settings.role(Role.chat)
    assert (chat.base_url, chat.api_key.get_secret_value(), chat.model) == (
        "https://default.invalid/v1",
        "test-key",
        "chat-model",
    )


def test_I11_base_url_defaults_to_openai_and_key_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("AI_ROUTER_MODEL", "from-env")
    monkeypatch.setenv("AI_EMBEDDING_DIMENSIONS", "8")
    monkeypatch.setenv("QDRANT_URL", "http://q:6333")
    settings = AISettings(_env_file=None)  # type: ignore[call-arg]
    router = settings.role(Role.router)
    assert router.base_url == "https://api.openai.com/v1"
    assert router.api_key.get_secret_value() == "env-key"
    assert router.model == "from-env"


def test_I11_a_role_without_a_model_is_not_configured() -> None:
    settings = settings_for("http://x/v1", ai_rerank_model=None)
    with pytest.raises(RoleNotConfigured, match="AI_RERANK_MODEL"):
        settings.role(Role.rerank)


def test_I11_no_model_names_in_code() -> None:
    offenders = [
        f"{path.relative_to(PACKAGE_SRC)}: {match.group(0)}"
        for path in PACKAGE_SRC.rglob("*.py")
        for match in MODEL_NAME_PATTERN.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


@pytest.mark.anyio()
async def test_I11_output_token_parameter_is_chosen_per_role(fake_openai: FakeOpenAI) -> None:
    settings = settings_for(fake_openai.base_url, ai_rewrite_output_token_param="max_tokens")
    clients = RoleClients(settings)
    try:
        fake_openai.queue(text_reply("a"), text_reply("b"))
        await clients.get(Role.chat).complete([{"role": "user", "content": "x"}], max_tokens=50)
        await clients.get(Role.rewrite).complete([{"role": "user", "content": "x"}], max_tokens=60)
    finally:
        await clients.aclose()
    chat_request, rewrite_request = fake_openai.chat_requests
    assert chat_request["model"] == "chat-model"
    assert chat_request["max_completion_tokens"] == 50 and "max_tokens" not in chat_request
    assert rewrite_request["model"] == "rewrite-model"
    assert rewrite_request["max_tokens"] == 60 and "max_completion_tokens" not in rewrite_request
