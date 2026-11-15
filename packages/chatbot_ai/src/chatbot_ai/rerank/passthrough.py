from __future__ import annotations

from chatbot_ai.rerank.base import RerankResult


class PassthroughReranker:
    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[RerankResult]:
        return [RerankResult(index=index, score=None) for index in range(min(top_n, len(documents)))]
