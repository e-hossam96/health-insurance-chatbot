from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient

from chatbot_ai.clients import RoleClients
from chatbot_ai.settings import AISettings
from testkit.ai_settings import settings_for
from testkit.fake_openai import FakeOpenAI, run_fake_openai
from testkit.qdrant import make_test_client


@pytest.fixture(scope="session")
def fake_openai_server() -> Iterator[FakeOpenAI]:
    with run_fake_openai() as fake:
        yield fake


@pytest.fixture()
def fake_openai(fake_openai_server: FakeOpenAI) -> Iterator[FakeOpenAI]:
    fake_openai_server.reset()
    yield fake_openai_server
    fake_openai_server.reset()


@pytest.fixture()
async def openai_client(fake_openai: FakeOpenAI) -> AsyncIterator[AsyncOpenAI]:
    client = AsyncOpenAI(api_key="test-key", base_url=fake_openai.base_url, max_retries=0, timeout=10.0)
    yield client
    await client.close()


@pytest.fixture()
async def qdrant() -> AsyncIterator[AsyncQdrantClient]:
    client = make_test_client()
    yield client
    await client.close()



@pytest.fixture()
def ai_settings(fake_openai: FakeOpenAI) -> AISettings:
    return settings_for(fake_openai.base_url)


@pytest.fixture()
async def role_clients(ai_settings: AISettings) -> AsyncIterator[RoleClients]:
    clients = RoleClients(ai_settings)
    yield clients
    await clients.aclose()
