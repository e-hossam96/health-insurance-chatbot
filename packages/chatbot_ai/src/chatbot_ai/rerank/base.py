from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from chatbot_ai.settings import AISettings


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float | None


class Reranker(Protocol):
    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[RerankResult]: ...


def make_reranker(settings: AISettings) -> Reranker:
    from chatbot_ai.rerank.passthrough import PassthroughReranker
    from chatbot_ai.rerank.target import TargetReranker

    if settings.ai_rerank_provider == "target":
        return TargetReranker(settings)
    return PassthroughReranker()
