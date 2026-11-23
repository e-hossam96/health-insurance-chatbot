from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from qdrant_client import models

from chatbot_ai.agents.knowledge import KnowledgeAgent
from chatbot_ai.clients import RoleClients
from chatbot_ai.ingest import ingest
from chatbot_ai.ingest.chunk import content_hash
from chatbot_ai.ingest.index import (
    DENSE_VECTOR,
    SPARSE_VECTOR,
    collection_name,
    document_filter,
    embed_sparse,
    make_qdrant,
)
from chatbot_ai.intents import AgentName
from chatbot_ai.interface import Done, ProfileInfo, TurnEvent, TurnRequest
from chatbot_ai.languages import LanguageCode
from chatbot_ai.orchestrator import default_agents, run_turn
from chatbot_ai.prompts import agent_system_prompt, load_prompt, reply_language_block
from chatbot_ai.rag.search import search_one
from chatbot_ai.rerank.base import RerankResult
from chatbot_ai.settings import AISettings
from testkit.ai_settings import settings_for
from testkit.embeddings import hash_embedding
from testkit.fake_openai import FakeOpenAI, json_reply, text_reply
from testkit.fake_ports import make_fake_ports, sample_catalog

FIXTURES = Path(__file__).resolve().parent.parent / "src" / "chatbot_ai" / "evals" / "kb_fixtures"
PROFILE = ProfileInfo(display_name="Mona", location_name="Cairo", location_id=1)
GUIDE, TWIN_A, TWIN_B = 2, 21, 22
TWIN_TEXT = "Orthodontic braces are covered once per member up to 9000 EGP."
SHARED_PHRASES = (
    "American English",
    "UTC",
    "Never give medical advice",
    "help them file a complaint",
    "fetch them again with a tool",
    "tool calls from tools you do not have now",
    "say plainly which part you cannot answer here",
    "Mona",
    "location id 1",
)


@pytest.fixture(scope="module")
def kb_model(fake_openai_server: FakeOpenAI, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    model = f"review-{uuid.uuid4().hex[:10]}"
    settings = settings_for(fake_openai_server.base_url, ai_embedding_model=model)
    folder = tmp_path_factory.mktemp("twins")
    for document_id in (TWIN_A, TWIN_B):
        path = folder / f"twin-{document_id}.txt"
        path.write_text(TWIN_TEXT, encoding="utf-8")
        ingest(document_id, str(path), "txt", settings)
    ingest(GUIDE, str(FIXTURES / "member_guide.docx"), "docx", settings)
    yield model

    async def drop() -> None:
        client = make_qdrant(settings)
        await client.delete_collection(collection_name(settings))
        await client.close()

    asyncio.run(drop())


class RecordingReranker:
    def __init__(self, reverse: bool = False, score: float | None = None) -> None:
        self.calls: list[tuple[str, list[str], int]] = []
        self.reverse = reverse
        self.score = score

    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[RerankResult]:
        self.calls.append((query, list(documents), top_n))
        order = list(reversed(range(len(documents)))) if self.reverse else list(range(len(documents)))
        return [RerankResult(index=i, score=self.score) for i in order[:top_n]]


async def _knowledge_turn(
    fake: FakeOpenAI,
    settings: AISettings,
    standalone: str,
    ready: list[int],
    reranker: RecordingReranker | None = None,
    answer: str = "Answer.",
    language: str = "en",
) -> list[TurnEvent]:
    fake.queue(json_reply({"intent": "qa.kb", "language": language}), model="router-model")
    fake.queue(json_reply({"standalone": standalone, "alternates": [f"{standalone} policy", f"{standalone} rules"]}), model="rewrite-model")
    fake.queue(text_reply(answer), model="chat-model")
    fakes = make_fake_ports(sample_catalog(), 10, 1, datetime(2026, 12, 1, tzinfo=UTC))
    fakes.knowledge.ready_ids.extend(ready)
    agents = dict(default_agents())
    if reranker is not None:
        agents[AgentName.knowledge] = KnowledgeAgent(lambda s: reranker)
    clients = RoleClients(settings)
    try:
        request = TurnRequest(history=[], message=standalone, profile=PROFILE, needs_label=False, session_id=9)
        return [e async for e in run_turn(request, fakes.as_ports(), settings, clients, agents)]
    finally:
        await clients.aclose()


def _excerpts(events: list[TurnEvent]) -> list[dict[str, str]]:
    done = events[-1]
    assert isinstance(done, Done)
    excerpts: list[dict[str, str]] = json.loads(done.new_rows[2].content)["excerpts"]
    return excerpts


def _answers(fake: FakeOpenAI) -> list[dict[str, object]]:
    return [r for r in fake.chat_requests if r["model"] == "chat-model"]


def test_I4_I14_F8_every_agent_gets_the_shared_blocks() -> None:
    for agent in AgentName:
        prompt = agent_system_prompt(agent, PROFILE, LanguageCode.english)
        for phrase in SHARED_PHRASES:
            assert phrase in prompt, f"{agent.value}: {phrase!r}"
    assert "tell them to ask for it separately" in agent_system_prompt(AgentName.knowledge, PROFILE, LanguageCode.english)


@pytest.mark.anyio()
async def test_I4_the_knowledge_answer_request_carries_the_full_agent_prompt(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=kb_model)
    await _knowledge_turn(fake_openai, settings, "Does an MRI scan need approval?", [GUIDE])
    system = str(_answers(fake_openai)[0]["messages"][0]["content"])  # type: ignore[index]
    assert system.startswith(agent_system_prompt(AgentName.knowledge, PROFILE, LanguageCode.english))
    assert system.endswith(reply_language_block(LanguageCode.english)), "F17: the reply language is repeated after the excerpts"
    assert system.index("Excerpts from the knowledge base documents") < system.rindex("American English")


@pytest.mark.anyio()
async def test_F17_an_other_language_knowledge_answer_ends_with_the_english_reminder(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=kb_model)
    await _knowledge_turn(fake_openai, settings, "Does an MRI scan need approval?", [GUIDE], language="other")
    messages = _answers(fake_openai)[0]["messages"]
    assert isinstance(messages, list)
    assert messages[-1] == {"role": "system", "content": load_prompt("language_other_reminder")}
    assert messages[-2]["role"] == "user"


@pytest.mark.anyio()
async def test_G4_every_point_has_dense_and_bm25_vectors_and_a_matching_content_hash(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=kb_model)
    client = make_qdrant(settings)
    try:
        records, _ = await client.scroll(
            collection_name(settings), scroll_filter=document_filter(GUIDE), limit=500, with_payload=True, with_vectors=True
        )
        assert records
        for record in records:
            vectors = record.vector
            assert isinstance(vectors, dict)
            assert len(vectors[DENSE_VECTOR]) == 64  # type: ignore[arg-type]
            sparse = vectors[SPARSE_VECTOR]
            assert isinstance(sparse, models.SparseVector) and sparse.indices
            assert record.payload is not None
            assert record.payload["content_hash"] == content_hash(record.payload["content"])
        mri = await search_one(
            client, collection_name(settings), hash_embedding("MRI", 64), embed_sparse(["MRI scan approval"], "query")[0], "sparse", 5, [GUIDE]
        )
        assert mri and "MRI scan" in mri[0].content
    finally:
        await client.close()


@pytest.mark.anyio()
async def test_I6_the_reranker_gets_the_standalone_and_merged_unique_candidates_and_sets_the_order(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=kb_model, ai_context_k=2, ai_fused_k=6)
    reranker = RecordingReranker(reverse=True)
    events = await _knowledge_turn(fake_openai, settings, "Which dental items need approval on the Premium tier?", [GUIDE, TWIN_A, TWIN_B], reranker)
    query, documents, top_n = reranker.calls[0]
    assert query == "Which dental items need approval on the Premium tier?"
    assert top_n == 2
    assert 0 < len(documents) <= 6
    assert len({content_hash(d) for d in documents}) == len(documents)
    excerpts = _excerpts(events)
    assert [e["content"] for e in excerpts] == [documents[-1], documents[-2]]


@pytest.mark.anyio()
async def test_I7_identical_text_in_two_documents_is_stored_twice_and_shown_once(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=kb_model)
    client = make_qdrant(settings)
    try:
        for document_id in (TWIN_A, TWIN_B):
            records, _ = await client.scroll(collection_name(settings), scroll_filter=document_filter(document_id), with_payload=True)
            assert [r.payload["content"] for r in records if r.payload] == [TWIN_TEXT]
    finally:
        await client.close()
    events = await _knowledge_turn(fake_openai, settings, "Are orthodontic braces covered?", [TWIN_A, TWIN_B, GUIDE])
    assert [e["content"] for e in _excerpts(events)].count(TWIN_TEXT) == 1


@pytest.mark.anyio()
async def test_I8_a_best_score_at_or_above_the_threshold_still_answers(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=kb_model, ai_rerank_min_score=0.5)
    await _knowledge_turn(fake_openai, settings, "Are orthodontic braces covered?", [TWIN_A], RecordingReranker(score=0.5), answer="Yes.")
    assert len(_answers(fake_openai)) == 1


@pytest.mark.anyio()
async def test_I8_without_rerank_scores_the_threshold_does_not_refuse(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=kb_model, ai_rerank_min_score=0.99)
    await _knowledge_turn(fake_openai, settings, "Are orthodontic braces covered?", [TWIN_A], answer="Yes.")
    assert len(_answers(fake_openai)) == 1


@pytest.mark.anyio()
async def test_I13_the_retrieval_mode_setting_changes_what_a_turn_finds(fake_openai: FakeOpenAI, kb_model: str) -> None:
    question = "zzqx unknownword"
    found: dict[str, list[dict[str, str]]] = {}
    for mode in ("sparse", "dense"):
        settings = settings_for(fake_openai.base_url, ai_embedding_model=kb_model, ai_retrieval_mode=mode)
        found[mode] = _excerpts(await _knowledge_turn(fake_openai, settings, question, [GUIDE]))
    assert found["sparse"] == []
    assert len(found["dense"]) == 5
    sparse_hit = _excerpts(
        await _knowledge_turn(fake_openai, settings_for(fake_openai.base_url, ai_embedding_model=kb_model, ai_retrieval_mode="sparse"), "MRI scan approval", [GUIDE])
    )
    assert "MRI scan" in sparse_hit[0]["content"]


@pytest.mark.anyio()
async def test_I13_the_target_rerank_provider_reaches_the_knowledge_agent(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = settings_for(fake_openai.base_url, ai_embedding_model=kb_model, ai_rerank_provider="target")
    with pytest.raises(NotImplementedError, match="Reranker provider not chosen yet"):
        await _knowledge_turn(fake_openai, settings, "Does an MRI scan need approval?", [GUIDE])
