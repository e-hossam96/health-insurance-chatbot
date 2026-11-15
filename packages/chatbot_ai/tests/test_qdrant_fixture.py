from __future__ import annotations

import pytest
from qdrant_client import AsyncQdrantClient, models

from testkit.embeddings import hash_embedding
from testkit.qdrant import temporary_collection

DIMENSIONS = 64
CHUNKS = [
    "Outpatient visits at network clinics have a co-pay of 50 EGP per visit.",
    "Hospital stays are covered up to 30 nights per year in a semi-private room.",
    "A rejected claim can be appealed once, in writing, within 30 days of the decision.",
]


def _sparse(text: str) -> models.SparseVector:
    vector = hash_embedding(text, 4096)
    indices = [i for i, v in enumerate(vector) if v != 0.0]
    return models.SparseVector(indices=indices, values=[abs(vector[i]) for i in indices])


@pytest.mark.anyio()
async def test_temporary_collection_supports_hybrid_search_and_is_dropped(qdrant: AsyncQdrantClient) -> None:
    async with temporary_collection(qdrant) as name:
        await qdrant.create_collection(
            name,
            vectors_config={"dense": models.VectorParams(size=DIMENSIONS, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        await qdrant.upsert(
            name,
            points=[
                models.PointStruct(
                    id=index,
                    vector={"dense": hash_embedding(text, DIMENSIONS), "sparse": _sparse(text)},
                    payload={"content": text},
                )
                for index, text in enumerate(CHUNKS)
            ],
            wait=True,
        )
        question = "how many nights of hospital stay are covered"
        result = await qdrant.query_points(
            name,
            prefetch=[
                models.Prefetch(query=hash_embedding(question, DIMENSIONS), using="dense", limit=3),
                models.Prefetch(query=_sparse(question), using="sparse", limit=3),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=3,
            with_payload=True,
        )
        assert result.points[0].payload is not None
        assert result.points[0].payload["content"] == CHUNKS[1]
        assert await qdrant.collection_exists(name)
    assert not await qdrant.collection_exists(name)
