from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from chatbot_ai.agents.knowledge import NOT_FOUND_REPLY, SEARCH_TOOL, KnowledgeAgent
from chatbot_ai.clients import RoleClients
from chatbot_ai.ingest import ingest
from chatbot_ai.ingest.index import collection_name, embed_sparse, make_qdrant
from chatbot_ai.intents import AgentName
from chatbot_ai.interface import Done, ProfileInfo, Token, TurnEvent, TurnRequest
from chatbot_ai.orchestrator import default_agents, run_turn
from chatbot_ai.rag.rewrite import rewrite_question
from chatbot_ai.rag.search import Candidate, dedupe, rrf_merge, search_one
from chatbot_ai.rerank.base import RerankResult, make_reranker
from chatbot_ai.rerank.passthrough import PassthroughReranker
from chatbot_ai.rerank.target import TargetReranker
from chatbot_ai.settings import AISettings, Role
from testkit.ai_settings import settings_for
from testkit.embeddings import hash_embedding
from testkit.fake_openai import FakeOpenAI, error_reply, json_reply, text_reply
from testkit.fake_ports import FakePorts, make_fake_ports, sample_catalog

FIXTURES = Path(__file__).resolve().parent.parent / "src" / "chatbot_ai" / "evals" / "kb_fixtures"
PROFILE = ProfileInfo(display_name="Mona", location_name="Cairo", location_id=1)
POLICY, GUIDE = 1, 2


@pytest.fixture(scope="module")
def kb_model(fake_openai_server: FakeOpenAI) -> Iterator[str]:
    model = f"rag-{uuid.uuid4().hex[:10]}"
    settings = settings_for(fake_openai_server.base_url, ai_embedding_model=model)
    ingest(POLICY, str(FIXTURES / "policy_handbook.pdf"), "pdf", settings)
    ingest(GUIDE, str(FIXTURES / "member_guide.docx"), "docx", settings)
    yield model

    async def drop() -> None:
        client = make_qdrant(settings)
        await client.delete_collection(collection_name(settings))
        await client.close()

    asyncio.run(drop())


def _settings(fake: FakeOpenAI, model: str, **overrides: object) -> AISettings:
    return settings_for(fake.base_url, ai_embedding_model=model, **overrides)


def _ports(ready: list[int]) -> FakePorts:
    fakes = make_fake_ports(sample_catalog(), 10, 1, datetime(2026, 12, 1, tzinfo=UTC))
    fakes.knowledge.ready_ids.extend(ready)
    return fakes


def _request(message: str) -> TurnRequest:
    return TurnRequest(history=[], message=message, profile=PROFILE, needs_label=False, session_id=5)


async def _turn(settings: AISettings, ready: list[int], message: str, agents: dict[AgentName, object] | None = None) -> list[TurnEvent]:
    clients = RoleClients(settings)
    try:
        registry = agents if agents is not None else default_agents()
        return [e async for e in run_turn(_request(message), _ports(ready).as_ports(), settings, clients, registry)]  # type: ignore[arg-type]
    finally:
        await clients.aclose()


def _queue_knowledge_turn(fake: FakeOpenAI, standalone: str, alternates: list[str], answer: str = "Here is the answer.") -> None:
    fake.queue(json_reply({"intent": "qa.kb"}), model="router-model")
    fake.queue(json_reply({"standalone": standalone, "alternates": alternates}), model="rewrite-model")
    fake.queue(text_reply(answer), model="chat-model")


def _answer_requests(fake: FakeOpenAI) -> list[dict[str, object]]:
    return [r for r in fake.chat_requests if r["model"] == "chat-model"]


def _candidate(point: str, content_hash: str = "") -> Candidate:
    return Candidate(point_id=point, content=point, headings=(), content_hash=content_hash or point, document_id=1)


def test_I7_rrf_merge_orders_by_reciprocal_rank() -> None:
    first = [_candidate("a"), _candidate("b"), _candidate("c")]
    second = [_candidate("c"), _candidate("a"), _candidate("d")]
    merged = rrf_merge([first, second], top_k=10, k=60)
    assert [c.point_id for c in merged] == ["a", "c", "b", "d"]
    assert merged[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert merged[0].sources == (0, 1)
    assert [c.point_id for c in rrf_merge([first, second], top_k=2)] == ["a", "c"]


def test_I7_dedupe_removes_repeated_ids_then_repeated_text() -> None:
    candidates = [_candidate("a", "h1"), _candidate("a", "h1"), _candidate("b", "h1"), _candidate("c", "h2")]
    assert [c.point_id for c in dedupe(candidates)] == ["a", "c"]


@pytest.mark.anyio()
async def test_I13_rewrite_asks_for_alternates_only_when_the_query_count_is_above_one(
    fake_openai: FakeOpenAI, role_clients: RoleClients
) -> None:
    fake_openai.queue(json_reply({"standalone": "Is maternity covered?", "alternates": ["maternity benefit", "pregnancy coverage"]}))
    three = await rewrite_question(role_clients.get(Role.rewrite), [], "and maternity?", 3)
    assert three.queries == ["Is maternity covered?", "maternity benefit", "pregnancy coverage"]
    schema = fake_openai.chat_requests[0]["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["standalone", "alternates"]

    fake_openai.queue(json_reply({"standalone": "Is maternity covered?"}))
    one = await rewrite_question(role_clients.get(Role.rewrite), [], "and maternity?", 1)
    assert one.queries == ["Is maternity covered?"]
    assert "alternates" not in fake_openai.chat_requests[1]["response_format"]["json_schema"]["schema"]["properties"]

    fake_openai.queue(error_reply(500))
    failed = await rewrite_question(role_clients.get(Role.rewrite), [], "raw question", 3)
    assert failed.queries == ["raw question"]


@pytest.mark.anyio()
async def test_I6_a_knowledge_turn_retrieves_the_expected_chunks_and_records_search_kb(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = _settings(fake_openai, kb_model)
    _queue_knowledge_turn(
        fake_openai, "How many days do I have to submit a reimbursement claim?", ["claim submission deadline", "reimbursement claim receipts days"],
        answer="Within 90 days of the service date.",
    )
    events = await _turn(settings, [POLICY, GUIDE], "how long for claims?")

    assert "".join(e.text for e in events if isinstance(e, Token)) == "Within 90 days of the service date."
    done = events[-1]
    assert isinstance(done, Done)
    assert [(r.role, r.tool_name) for r in done.new_rows] == [("user", None), ("assistant", None), ("tool", SEARCH_TOOL), ("assistant", None)]
    call = done.new_rows[1].tool_calls
    assert call is not None and call[0]["function"]["name"] == SEARCH_TOOL
    assert json.loads(call[0]["function"]["arguments"]) == {"query": "How many days do I have to submit a reimbursement claim?"}
    excerpts = json.loads(done.new_rows[2].content)["excerpts"]
    assert len(excerpts) <= settings.ai_context_k
    claims = next(e for e in excerpts if "within 90 days" in e["content"])
    assert claims["section"] == "4 Claims > 4.1 Submitting a claim"

    system_prompt = str(_answer_requests(fake_openai)[0]["messages"][0]["content"])  # type: ignore[index]
    assert "4 Claims > 4.1 Submitting a claim\nSubmit reimbursement claims within 90 days" in system_prompt
    assert "Answer only from the excerpts" in system_prompt
    assert len(fake_openai.embedding_requests[-1]["input"]) == 3
    assert done.timings.rewrite >= 0 and done.timings.search > 0 and done.timings.embed > 0


@pytest.mark.anyio()
async def test_I6_a_docx_table_question_finds_the_table_chunk(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = _settings(fake_openai, kb_model)
    _queue_knowledge_turn(fake_openai, "Which services need approval and what is the lead time for an MRI scan?", [])
    events = await _turn(settings, [POLICY, GUIDE], "does an MRI need approval?")
    done = events[-1]
    assert isinstance(done, Done)
    excerpts = json.loads(done.new_rows[2].content)["excerpts"]
    table = next(e for e in excerpts if "| MRI scan | Yes | 3 working days |" in e["content"])
    assert table["section"] == "Pre-authorization > Services that need approval"


@pytest.mark.anyio()
async def test_G8_only_ready_documents_are_searchable(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = _settings(fake_openai, kb_model)
    _queue_knowledge_turn(fake_openai, "Which services need approval and what is the lead time for an MRI scan?", [])
    events = await _turn(settings, [POLICY], "does an MRI need approval?")
    done = events[-1]
    assert isinstance(done, Done)
    excerpts = json.loads(done.new_rows[2].content)["excerpts"]
    assert excerpts and not any("MRI scan" in e["content"] for e in excerpts)


@pytest.mark.anyio()
async def test_I8_no_ready_documents_gives_the_fixed_reply_without_a_chat_call(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = _settings(fake_openai, kb_model)
    fake_openai.queue(json_reply({"intent": "qa.kb"}), model="router-model")
    fake_openai.queue(json_reply({"standalone": "Is cosmetic surgery covered?", "alternates": []}), model="rewrite-model")
    events = await _turn(settings, [], "cosmetic surgery?")
    assert [e.text for e in events if isinstance(e, Token)] == [NOT_FOUND_REPLY]
    assert NOT_FOUND_REPLY == "I couldn't find that in the documents."
    done = events[-1]
    assert isinstance(done, Done)
    assert done.new_rows[-1].content == NOT_FOUND_REPLY
    assert _answer_requests(fake_openai) == []
    assert fake_openai.embedding_requests == []


class LowScoreReranker:
    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[RerankResult]:
        return [RerankResult(index=i, score=0.1) for i in range(min(top_n, len(documents)))]


@pytest.mark.anyio()
async def test_I8_a_best_score_below_the_threshold_gives_the_fixed_reply(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = _settings(fake_openai, kb_model, ai_rerank_min_score=0.5)
    fake_openai.queue(json_reply({"intent": "qa.kb"}), model="router-model")
    fake_openai.queue(json_reply({"standalone": "Is cosmetic surgery covered?", "alternates": []}), model="rewrite-model")
    agents = {**default_agents(), AgentName.knowledge: KnowledgeAgent(lambda s: LowScoreReranker())}
    events = await _turn(settings, [POLICY, GUIDE], "cosmetic surgery?", agents)  # type: ignore[arg-type]
    assert [e.text for e in events if isinstance(e, Token)] == [NOT_FOUND_REPLY]
    assert _answer_requests(fake_openai) == []
    assert len(fake_openai.embedding_requests) == 1


@pytest.mark.anyio()
async def test_I9_I10_a_knowledge_turn_makes_no_verifier_call_and_nothing_is_cached(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = _settings(fake_openai, kb_model)
    for _ in range(2):
        _queue_knowledge_turn(fake_openai, "Is cosmetic surgery covered?", [], answer="No, it is excluded.")
        await _turn(settings, [POLICY, GUIDE], "Is cosmetic surgery covered?")
    assert [r["model"] for r in fake_openai.chat_requests] == ["router-model", "rewrite-model", "chat-model"] * 2
    assert len(fake_openai.embedding_requests) == 2
    assert fake_openai.pending() == 0


@pytest.mark.anyio()
async def test_I13_retrieval_mode_switches_between_dense_sparse_and_hybrid(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = _settings(fake_openai, kb_model)
    client = make_qdrant(settings)
    collection = collection_name(settings)
    try:
        unknown_words = "zzqx qqvv"
        dense = hash_embedding(unknown_words, 64)
        sparse = embed_sparse([unknown_words], "query")[0]
        results = {
            mode: await search_one(client, collection, dense, sparse, mode, 5, [POLICY, GUIDE])  # type: ignore[arg-type]
            for mode in ("dense", "sparse", "hybrid")
        }
    finally:
        await client.close()
    assert results["sparse"] == []
    assert len(results["dense"]) == 5
    assert len(results["hybrid"]) == 5


@pytest.mark.anyio()
async def test_I13_query_count_changes_the_number_of_searched_queries(fake_openai: FakeOpenAI, kb_model: str) -> None:
    settings = _settings(fake_openai, kb_model, ai_query_count=1)
    fake_openai.queue(json_reply({"intent": "qa.kb"}), model="router-model")
    fake_openai.queue(json_reply({"standalone": "Is cosmetic surgery covered?"}), model="rewrite-model")
    fake_openai.queue(text_reply("No."), model="chat-model")
    await _turn(settings, [POLICY], "cosmetic?")
    assert fake_openai.embedding_requests[0]["input"] == ["Is cosmetic surgery covered?"]


@pytest.mark.anyio()
async def test_I13_the_rerank_provider_switch_and_the_target_placeholder() -> None:
    base = settings_for("http://x/v1")
    assert isinstance(make_reranker(base), PassthroughReranker)
    target = make_reranker(settings_for("http://x/v1", ai_rerank_provider="target"))
    assert isinstance(target, TargetReranker)
    with pytest.raises(NotImplementedError, match="Reranker provider not chosen yet"):
        await target.rerank("q", ["a"], 1)
    kept = await PassthroughReranker().rerank("q", ["a", "b", "c"], 2)
    assert kept == [RerankResult(0, None), RerankResult(1, None)]


@pytest.mark.anyio()
async def test_I4_I14_knowledge_then_scheduling_keeps_each_agent_to_its_own_tools(fake_openai: FakeOpenAI, kb_model: str) -> None:
    from testkit.fake_openai import ToolCallSpec, tool_reply

    settings = _settings(fake_openai, kb_model)
    fakes = _ports([POLICY, GUIDE])
    clients = RoleClients(settings)
    try:
        _queue_knowledge_turn(fake_openai, "Is physiotherapy covered?", [], answer="Physiotherapy is covered for 24 sessions.")
        knowledge = [e async for e in run_turn(_request("Is physiotherapy covered?"), fakes.as_ports(), settings, clients)]
        knowledge_done = knowledge[-1]
        assert isinstance(knowledge_done, Done)
        assert "tools" not in _answer_requests(fake_openai)[0]

        fake_openai.queue(json_reply({"intent": "visit.book"}), model="router-model")
        fake_openai.queue(
            tool_reply(ToolCallSpec(SEARCH_TOOL, {"query": "physiotherapy"}, id="k1")),
            text_reply("Which specialty do you need?"),
            model="chat-model",
        )
        follow_up = TurnRequest(history=knowledge_done.new_rows, message="book a session", profile=PROFILE, needs_label=False, session_id=5)
        scheduling = [e async for e in run_turn(follow_up, fakes.as_ports(), settings, clients)]
    finally:
        await clients.aclose()

    scheduling_done = scheduling[-1]
    assert isinstance(scheduling_done, Done)
    foreign = next(r for r in scheduling_done.new_rows if r.tool_call_id == "k1")
    assert "not available here" in foreign.content
    assert fakes.scheduling.calls == []
    offered = {t["function"]["name"] for t in _answer_requests(fake_openai)[1]["tools"]}  # type: ignore[union-attr]
    assert SEARCH_TOOL not in offered and "recommend_doctors" in offered
