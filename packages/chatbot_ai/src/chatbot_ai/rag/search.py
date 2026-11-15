from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from qdrant_client import AsyncQdrantClient, models

from chatbot_ai.ingest.index import DENSE_VECTOR, SPARSE_VECTOR
from chatbot_ai.settings import RetrievalMode

RRF_K = 60


@dataclass(frozen=True)
class Candidate:
    point_id: str
    content: str
    headings: tuple[str, ...]
    content_hash: str
    document_id: int
    score: float = 0.0
    rerank_score: float | None = None
    sources: tuple[int, ...] = field(default_factory=tuple)

    @property
    def breadcrumb(self) -> str:
        return " > ".join(self.headings)


def ready_filter(document_ids: Sequence[int]) -> models.Filter:
    return models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchAny(any=list(document_ids)))])


def _candidate(point: models.ScoredPoint) -> Candidate:
    payload = point.payload or {}
    return Candidate(
        point_id=str(point.id),
        content=str(payload.get("content", "")),
        headings=tuple(str(h) for h in payload.get("headings", [])),
        content_hash=str(payload.get("content_hash", "")),
        document_id=int(payload.get("document_id", 0)),
        score=point.score,
    )


async def search_one(
    client: AsyncQdrantClient,
    collection: str,
    dense: list[float],
    sparse: models.SparseVector,
    mode: RetrievalMode,
    prefetch_k: int,
    document_ids: Sequence[int],
) -> list[Candidate]:
    query_filter = ready_filter(document_ids)
    if mode == "dense":
        result = await client.query_points(
            collection, query=dense, using=DENSE_VECTOR, limit=prefetch_k, query_filter=query_filter, with_payload=True
        )
    elif mode == "sparse":
        result = await client.query_points(
            collection, query=sparse, using=SPARSE_VECTOR, limit=prefetch_k, query_filter=query_filter, with_payload=True
        )
    else:
        result = await client.query_points(
            collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE_VECTOR, limit=prefetch_k, filter=query_filter),
                models.Prefetch(query=sparse, using=SPARSE_VECTOR, limit=prefetch_k, filter=query_filter),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=prefetch_k,
            with_payload=True,
        )
    return [_candidate(point) for point in result.points]


def rrf_merge(ranked_lists: Sequence[Sequence[Candidate]], top_k: int, k: int = RRF_K) -> list[Candidate]:
    scores: dict[str, float] = {}
    first_seen: dict[str, Candidate] = {}
    sources: dict[str, list[int]] = {}
    for list_index, ranked in enumerate(ranked_lists):
        for rank, candidate in enumerate(ranked, start=1):
            scores[candidate.point_id] = scores.get(candidate.point_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(candidate.point_id, candidate)
            sources.setdefault(candidate.point_id, []).append(list_index)
    ordered = sorted(scores, key=lambda point: (-scores[point], point))
    return [
        Candidate(
            point_id=point,
            content=first_seen[point].content,
            headings=first_seen[point].headings,
            content_hash=first_seen[point].content_hash,
            document_id=first_seen[point].document_id,
            score=scores[point],
            sources=tuple(sources[point]),
        )
        for point in ordered[:top_k]
    ]


def dedupe(candidates: Sequence[Candidate]) -> list[Candidate]:
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    unique: list[Candidate] = []
    for candidate in candidates:
        if candidate.point_id in seen_ids:
            continue
        seen_ids.add(candidate.point_id)
        if candidate.content_hash and candidate.content_hash in seen_hashes:
            continue
        seen_hashes.add(candidate.content_hash)
        unique.append(candidate)
    return unique
