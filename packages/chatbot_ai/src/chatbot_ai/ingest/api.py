from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from chatbot_ai.clients import RoleClients
from chatbot_ai.ingest.chunk import chunk_blocks
from chatbot_ai.ingest.index import (
    delete_points,
    embed_dense,
    embed_sparse,
    ensure_collection_async,
    make_qdrant,
    upsert_chunks,
)
from chatbot_ai.ingest.parse import FileType, parse_document
from chatbot_ai.settings import AISettings, Role


@dataclass(frozen=True)
class IngestTimings:
    parse: float
    chunk: float
    embed: float
    upsert: float


@dataclass(frozen=True)
class IngestResult:
    chunk_count: int
    table_chunks: int
    timings: IngestTimings


async def _ingest(document_id: int, file_path: Path, file_type: FileType, settings: AISettings) -> IngestResult:
    started = time.monotonic()
    blocks = parse_document(file_path, file_type)
    parsed = time.monotonic()
    chunks = chunk_blocks(blocks, settings.ai_chunk_max_tokens)
    chunked = time.monotonic()

    clients = RoleClients(settings)
    qdrant = make_qdrant(settings)
    try:
        texts = [chunk.embed_text for chunk in chunks]
        dense = await embed_dense(clients.get(Role.embedding), texts, "document", settings)
        sparse = embed_sparse(texts, "document")
        embedded = time.monotonic()
        collection = await ensure_collection_async(qdrant, settings)
        await delete_points(qdrant, collection, document_id)
        await upsert_chunks(qdrant, collection, document_id, chunks, dense, sparse)
        upserted = time.monotonic()
    finally:
        await clients.aclose()
        await qdrant.close()

    return IngestResult(
        chunk_count=len(chunks),
        table_chunks=sum(1 for chunk in chunks if chunk.kind == "table"),
        timings=IngestTimings(parse=parsed - started, chunk=chunked - parsed, embed=embedded - chunked, upsert=upserted - embedded),
    )


def ingest(document_id: int, file_path: str, file_type: FileType, settings: AISettings) -> IngestResult:
    return asyncio.run(_ingest(document_id, Path(file_path), file_type, settings))


async def delete_document_async(document_id: int, settings: AISettings) -> None:
    qdrant = make_qdrant(settings)
    try:
        collection = await ensure_collection_async(qdrant, settings)
        await delete_points(qdrant, collection, document_id)
    finally:
        await qdrant.close()


def delete_document(document_id: int, settings: AISettings) -> None:
    asyncio.run(delete_document_async(document_id, settings))


async def ensure_collection_once(settings: AISettings) -> str:
    qdrant = make_qdrant(settings)
    try:
        return await ensure_collection_async(qdrant, settings)
    finally:
        await qdrant.close()


def ensure_collection(settings: AISettings) -> str:
    return asyncio.run(ensure_collection_once(settings))
