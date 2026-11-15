from __future__ import annotations

from chatbot_ai.rerank.base import RerankResult
from chatbot_ai.settings import AISettings, Role


class TargetReranker:
    def __init__(self, settings: AISettings) -> None:
        self.settings = settings
        self.role = Role.rerank

    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[RerankResult]:
        raise NotImplementedError("Reranker provider not chosen yet")
