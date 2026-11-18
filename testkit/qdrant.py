from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from qdrant_client import AsyncQdrantClient

DEFAULT_QDRANT_URL = "http://127.0.0.1:6333"


def qdrant_url() -> str:
    return os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL)


def make_test_client() -> AsyncQdrantClient:
    # the compose and CI image may lag the client by a few minor versions; the tests exercise the real server
    return AsyncQdrantClient(url=qdrant_url())


@asynccontextmanager
async def temporary_collection(client: AsyncQdrantClient, prefix: str = "test") -> AsyncIterator[str]:
    name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    try:
        yield name
    finally:
        if await client.collection_exists(name):
            await client.delete_collection(name)
