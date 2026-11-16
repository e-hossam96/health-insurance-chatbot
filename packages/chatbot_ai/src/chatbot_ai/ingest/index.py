from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from functools import cache
from typing import TYPE_CHECKING, Literal

from qdrant_client import AsyncQdrantClient, models

from chatbot_ai.clients import RoleClient
from chatbot_ai.ingest.chunk import Chunk
from chatbot_ai.settings import AISettings

if TYPE_CHECKING:
    from fastembed import SparseTextEmbedding

POINT_NAMESPACE = uuid.UUID("6f1c2b52-6c55-4c39-9d3a-1d8a4b0f2e11")
DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"
BM25_MODEL = "Qdrant/bm25"
EmbedKind = Literal["query", "document"]


def collection_name(settings: AISettings) -> str:
    if settings.ai_qdrant_collection:
        return settings.ai_qdrant_collection
    model = settings.ai_embedding_model or "unset"
    slug = re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_")
    return f"kb_{slug}_{settings.ai_embedding_dimensions}"


def point_id(document_id: int, chunk_index: int) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, f"{document_id}:{chunk_index}"))


def make_qdrant(settings: AISettings) -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_url, check_compatibility=False)


async def ensure_collection_async(client: AsyncQdrantClient, settings: AISettings) -> str:
    name = collection_name(settings)
    if not await client.collection_exists(name):
        await client.create_collection(
            name,
            vectors_config={
                DENSE_VECTOR: models.VectorParams(size=settings.ai_embedding_dimensions, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        await client.create_payload_index(name, "document_id", models.PayloadSchemaType.INTEGER)
    return name


def _prefixed(texts: Sequence[str], kind: EmbedKind, settings: AISettings) -> list[str]:
    prefix = settings.ai_embedding_query_prefix if kind == "query" else settings.ai_embedding_doc_prefix
    return [f"{prefix}{text}" for text in texts]


async def embed_dense(embedder: RoleClient, texts: Sequence[str], kind: EmbedKind, settings: AISettings) -> list[list[float]]:
    vectors: list[list[float]] = []
    prefixed = _prefixed(texts, kind, settings)
    for start in range(0, len(prefixed), settings.ai_embed_batch):
        batch = prefixed[start : start + settings.ai_embed_batch]
        response = await embedder.client.embeddings.create(
            model=embedder.model, input=batch, dimensions=settings.ai_embedding_dimensions
        )
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
    if any(len(v) != settings.ai_embedding_dimensions for v in vectors):
        raise ValueError("the embedding provider returned vectors of the wrong size")
    return vectors


@cache
def _bm25() -> SparseTextEmbedding:
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(BM25_MODEL)


def embed_sparse(texts: Sequence[str], kind: EmbedKind) -> list[models.SparseVector]:
    model = _bm25()
    embedded = model.query_embed(list(texts)) if kind == "query" else model.embed(list(texts))
    return [models.SparseVector(indices=e.indices.tolist(), values=e.values.tolist()) for e in embedded]


def document_filter(document_id: int) -> models.Filter:
    return models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))])


async def delete_points(client: AsyncQdrantClient, collection: str, document_id: int) -> None:
    await client.delete(collection, points_selector=models.FilterSelector(filter=document_filter(document_id)), wait=True)


async def upsert_chunks(
    client: AsyncQdrantClient,
    collection: str,
    document_id: int,
    chunks: Sequence[Chunk],
    dense: Sequence[list[float]],
    sparse: Sequence[models.SparseVector],
) -> None:
    points = [
        models.PointStruct(
            id=point_id(document_id, chunk.index),
            vector={DENSE_VECTOR: dense_vector, SPARSE_VECTOR: sparse_vector},
            payload={
                "document_id": document_id,
                "chunk_index": chunk.index,
                "content": chunk.content,
                "headings": list(chunk.headings),
                "kind": chunk.kind,
                "content_hash": chunk.content_hash,
            },
        )
        for chunk, dense_vector, sparse_vector in zip(chunks, dense, sparse, strict=True)
    ]
    try:
        await client.upsert(collection, points=points, wait=True)
    except Exception:
        await delete_points(client, collection, document_id)
        raise
