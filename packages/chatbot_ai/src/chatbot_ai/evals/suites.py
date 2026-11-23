from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import BaseModel

from chatbot_ai.agents.base import AgentContext, AgentResult
from chatbot_ai.agents.knowledge import KnowledgeAgent
from chatbot_ai.clients import RoleClients
from chatbot_ai.evals.catalog_ports import make_fake_ports, sample_catalog
from chatbot_ai.evals.schemas import AnswerItem, RetrievalItem, ToolScenario
from chatbot_ai.ingest import ingest
from chatbot_ai.ingest.chunk import chunk_blocks, render_table
from chatbot_ai.ingest.index import (
    collection_name,
    embed_dense,
    embed_sparse,
    make_qdrant,
)
from chatbot_ai.ingest.parse import FileType, TableBlock, parse_document
from chatbot_ai.interface import (
    Cards,
    Done,
    HistoryRow,
    Intent,
    ProfileInfo,
    Token,
    TurnRequest,
)
from chatbot_ai.languages import LanguageCode, display_language, written_language
from chatbot_ai.orchestrator import run_turn
from chatbot_ai.rag.rewrite import rewrite_question
from chatbot_ai.rag.search import Candidate, dedupe, rrf_merge, search_one
from chatbot_ai.rerank.base import make_reranker
from chatbot_ai.settings import AISettings, Role
from chatbot_ai.tools.ports import Ports
from chatbot_ai.tracing import NoopTracer

EVALS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = EVALS_DIR / "kb_fixtures"
FIXTURE_DOCUMENTS: dict[str, tuple[int, FileType]] = {"policy_handbook.pdf": (1, "pdf"), "member_guide.docx": (2, "docx")}
DOCUMENT_IDS = [document_id for document_id, _ in FIXTURE_DOCUMENTS.values()]
EVAL_NOW = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
PROFILE = ProfileInfo(display_name="Eval Member", location_name="Cairo", location_id=1)
KS = (5, 10)
JUDGE_SCHEMA: ResponseFormatJSONSchema = {
    "type": "json_schema",
    "json_schema": {
        "name": "judge",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "faithful": {"type": "boolean"},
                "facts_present": {"type": "boolean"},
                "refused": {"type": "boolean"},
                "notes": {"type": "string"},
            },
            "required": ["faithful", "facts_present", "refused", "notes"],
            "additionalProperties": False,
        },
    },
}


class IngestReport(BaseModel):
    documents: dict[str, dict[str, int | float]]
    empty_chunks: int
    chunks_without_breadcrumb: int
    split_tables_missing_header: int
    passed: bool


class StageScores(BaseModel):
    hit: dict[str, float]
    recall: dict[str, float]
    mrr: float


class RetrievalReport(BaseModel):
    items: int
    stages: dict[str, StageScores]
    mean_latency_s: dict[str, float]
    misses: list[str]


class AnswerOutcome(BaseModel):
    id: str
    answerable: bool
    answer: str
    facts_found: bool
    judged_faithful: bool | None
    judged_facts_present: bool | None
    refused: bool
    correct_refusal: bool
    expected_language: str = LanguageCode.english.value
    reply_language: str = LanguageCode.english.value


class AnswersReport(BaseModel):
    items: int
    faithfulness: float
    facts_present: float
    refusal_accuracy: float
    reply_language_accuracy: float
    judge_errors: int
    outcomes: list[AnswerOutcome]


class TurnOutcome(BaseModel):
    scenario: str
    turn: int
    expected_intent: str
    intent: str | None
    tools: list[str]
    cards: str | None
    foreign_tool_calls: int
    stale_slot_mentions: int = 0
    expected_language: str = LanguageCode.english.value
    reply_language: str = LanguageCode.english.value
    card_language: str | None = None
    passed: bool


class ToolsReport(BaseModel):
    scenarios: int
    turns: int
    turn_pass_rate: float
    scenario_pass_rate: float
    language_pass_rate: float
    outcomes: list[TurnOutcome]


def eval_settings(settings: AISettings) -> AISettings:
    return settings.model_copy(update={"ai_qdrant_collection": f"eval_{uuid.uuid4().hex[:12]}"})


@asynccontextmanager
async def fixture_collection(settings: AISettings) -> AsyncIterator[AISettings]:
    scoped = eval_settings(settings)
    try:
        for name, (document_id, file_type) in FIXTURE_DOCUMENTS.items():
            await asyncio.to_thread(ingest, document_id, str(FIXTURES_DIR / name), file_type, scoped)
        yield scoped
    finally:
        client = make_qdrant(scoped)
        try:
            if await client.collection_exists(collection_name(scoped)):
                await client.delete_collection(collection_name(scoped))
        finally:
            await client.close()


def run_ingest_suite(settings: AISettings) -> IngestReport:
    documents: dict[str, dict[str, int | float]] = {}
    empty = no_breadcrumb = missing_header = 0
    for name, (_, file_type) in FIXTURE_DOCUMENTS.items():
        started = time.monotonic()
        blocks = parse_document(FIXTURES_DIR / name, file_type)
        chunks = chunk_blocks(blocks, settings.ai_chunk_max_tokens)
        empty += sum(1 for c in chunks if not c.content.strip())
        no_breadcrumb += sum(1 for c in chunks if not c.headings)
        for table in (b for b in blocks if isinstance(b, TableBlock)):
            header = render_table(table.header, [])
            pieces = chunk_blocks([table], settings.ai_chunk_max_tokens)
            missing_header += sum(1 for p in pieces if not p.content.startswith(header))
        documents[name] = {
            "chunks": len(chunks),
            "table_chunks": sum(1 for c in chunks if c.kind == "table"),
            "tables": sum(1 for b in blocks if isinstance(b, TableBlock)),
            "parse_and_chunk_s": round(time.monotonic() - started, 3),
        }
    return IngestReport(
        documents=documents,
        empty_chunks=empty,
        chunks_without_breadcrumb=no_breadcrumb,
        split_tables_missing_header=missing_header,
        passed=empty == 0 and missing_header == 0,
    )


@dataclass
class _Totals:
    hit: dict[int, float] = field(default_factory=lambda: {k: 0.0 for k in KS})
    recall: dict[int, float] = field(default_factory=lambda: {k: 0.0 for k in KS})
    mrr: float = 0.0

    def add(self, hits: dict[int, bool], recall: dict[int, float], mrr: float) -> None:
        for k in KS:
            self.hit[k] += float(hits[k])
            self.recall[k] += recall[k]
        self.mrr += mrr


def _relevant(candidate: Candidate, item: RetrievalItem) -> bool:
    expected_id = FIXTURE_DOCUMENTS[item.expected_document][0]
    return candidate.document_id == expected_id and any(phrase in candidate.content for phrase in item.expected_phrases)


def _scores(ranked: Sequence[Candidate], item: RetrievalItem) -> tuple[dict[int, bool], dict[int, float], float]:
    hits = {k: any(_relevant(c, item) for c in ranked[:k]) for k in KS}
    recall = {
        k: sum(1 for phrase in item.expected_phrases if any(phrase in c.content for c in ranked[:k])) / len(item.expected_phrases)
        for k in KS
    }
    rank = next((i for i, c in enumerate(ranked[: max(KS)], start=1) if _relevant(c, item)), None)
    return hits, recall, (1.0 / rank) if rank else 0.0


async def run_retrieval_suite(settings: AISettings, items: list[RetrievalItem]) -> RetrievalReport:
    stages = ("first_query", "fused", "deduped", "reranked")
    totals = {s: _Totals() for s in stages}
    latency = {"rewrite": 0.0, "embed": 0.0, "search": 0.0, "rerank": 0.0}
    misses: list[str] = []
    async with fixture_collection(settings) as scoped:
        clients = RoleClients(scoped)
        qdrant = make_qdrant(scoped)
        try:
            for item in items:
                t0 = time.monotonic()
                rewrite = await rewrite_question(clients.get(Role.rewrite), [], item.question, scoped.ai_query_count, scoped.ai_rewrite_max_output_tokens)
                t1 = time.monotonic()
                dense = await embed_dense(clients.get(Role.embedding), rewrite.queries, "query", scoped)
                sparse = embed_sparse(rewrite.queries, "query")
                t2 = time.monotonic()
                lists = [
                    await search_one(qdrant, collection_name(scoped), d, s, scoped.ai_retrieval_mode, scoped.ai_prefetch_k, DOCUMENT_IDS)
                    for d, s in zip(dense, sparse, strict=True)
                ]
                fused = rrf_merge(lists, scoped.ai_fused_k)
                deduped = dedupe(fused)
                t3 = time.monotonic()
                reranked_order = await make_reranker(scoped).rerank(rewrite.standalone, [c.content for c in deduped], max(KS))
                reranked = [replace(deduped[r.index], rerank_score=r.score) for r in reranked_order]
                t4 = time.monotonic()
                for name, ranked in zip(stages, (lists[0], fused, deduped, reranked), strict=True):
                    hits, recall, mrr = _scores(ranked, item)
                    totals[name].add(hits, recall, mrr)
                if not _scores(reranked, item)[0][max(KS)]:
                    misses.append(item.id)
                for key, seconds in (("rewrite", t1 - t0), ("embed", t2 - t1), ("search", t3 - t2), ("rerank", t4 - t3)):
                    latency[key] += seconds
        finally:
            await qdrant.close()
            await clients.aclose()
    n = max(len(items), 1)
    return RetrievalReport(
        items=len(items),
        stages={
            s: StageScores(
                hit={f"@{k}": totals[s].hit[k] / n for k in KS},
                recall={f"@{k}": totals[s].recall[k] / n for k in KS},
                mrr=totals[s].mrr / n,
            )
            for s in stages
        },
        mean_latency_s={key: value / n for key, value in latency.items()},
        misses=misses,
    )


def eval_ports(ready: list[int]) -> Ports:
    fakes = make_fake_ports(sample_catalog(), profile_id=10, profile_location_id=1, now=EVAL_NOW)
    fakes.knowledge.ready_ids.extend(ready)
    return fakes.as_ports()


async def _judge(clients: RoleClients, item: AnswerItem, answer: str, excerpts: str) -> tuple[bool, bool, bool] | None:
    prompt = (
        "You grade an insurance assistant's answer. Excerpts it was given:\n"
        f"{excerpts}\n\nQuestion: {item.question}\nAnswer: {answer}\n"
        f"Required facts: {item.must_include}\n"
        "faithful: every claim in the answer is supported by the excerpts. facts_present: every required fact is in the answer. "
        "refused: the answer says it could not find the information. "
        "The answer may be in Arabic while the excerpts are in English: judge by meaning, and accept amounts, days and numbers in either language."
    )
    try:
        judge = clients.get(Role.judge)
        completion = await judge.complete([{"role": "user", "content": prompt}], max_tokens=1024, response_format=JUDGE_SCHEMA)
        verdict = json.loads(completion.choices[0].message.content or "")
        return bool(verdict["faithful"]), bool(verdict["facts_present"]), bool(verdict["refused"])
    except Exception:  # noqa: BLE001 - a failed judgement is counted, not fatal
        return None


async def run_answers_suite(settings: AISettings, items: list[AnswerItem]) -> AnswersReport:
    ports = eval_ports(DOCUMENT_IDS)
    outcomes: list[AnswerOutcome] = []
    judge_errors = 0
    async with fixture_collection(settings) as scoped:
        clients = RoleClients(scoped)
        try:
            for item in items:
                request = TurnRequest(history=[], message=item.question, profile=PROFILE, needs_label=False, session_id=0)
                context = AgentContext(
                    request=request,
                    ports=ports,
                    settings=scoped,
                    clients=clients,
                    clock=time.monotonic,
                    tracer=NoopTracer(),
                    language=item.expected_language,
                )
                answer = ""
                result: AgentResult | None = None
                async for event in KnowledgeAgent().run(context):
                    if isinstance(event, Token):
                        answer += event.text
                    elif isinstance(event, AgentResult):
                        result = event
                excerpts = result.rows[1].content if result and len(result.rows) > 1 else "{}"
                verdict = await _judge(clients, item, answer, excerpts)
                judge_errors += verdict is None
                refused = is_refusal(answer, verdict[2] if verdict is not None else None)
                outcomes.append(
                    AnswerOutcome(
                        id=item.id,
                        answerable=item.answerable,
                        answer=answer,
                        facts_found=item.facts_in(answer),
                        judged_faithful=verdict[0] if verdict else None,
                        judged_facts_present=verdict[1] if verdict else None,
                        refused=refused,
                        correct_refusal=refused != item.answerable,
                        expected_language=item.expected_language.value,
                        reply_language=written_language(answer).value,
                    )
                )
        finally:
            await clients.aclose()
    answerable = [o for o in outcomes if o.answerable]
    judged = [o for o in answerable if o.judged_faithful is not None]
    return AnswersReport(
        items=len(outcomes),
        faithfulness=sum(1 for o in judged if o.judged_faithful) / max(len(judged), 1),
        facts_present=sum(1 for o in answerable if o.facts_found) / max(len(answerable), 1),
        refusal_accuracy=sum(1 for o in outcomes if o.correct_refusal) / max(len(outcomes), 1),
        reply_language_accuracy=sum(1 for o in outcomes if o.reply_language == display_language(LanguageCode(o.expected_language)).value)
        / max(len(outcomes), 1),
        judge_errors=judge_errors,
        outcomes=outcomes,
    )


TOOL_RESULT_CLOCK = re.compile(r"T(\d{2}:\d{2})")
ANSWER_CLOCK = re.compile(r"\b(\d{2}:\d{2})\b")


def is_refusal(answer: str, judged_refusal: bool | None) -> bool:
    if judged_refusal is not None:
        return judged_refusal
    return answer.lower().lstrip().startswith(("i couldn't find", "i could not find", "لم أجد", "لم اجد"))


def stale_slot_mentions(earlier_tool_results: str, current_tool_results: str, answer: str) -> int:
    stale = set(TOOL_RESULT_CLOCK.findall(earlier_tool_results)) - set(TOOL_RESULT_CLOCK.findall(current_tool_results))
    return len(set(ANSWER_CLOCK.findall(answer)) & stale)


def _subset(expected: dict[str, object], actual: dict[str, object]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


async def run_tools_suite(
    settings: AISettings, scenarios: list[ToolScenario], ports_factory: Callable[[list[int]], Ports] = eval_ports
) -> ToolsReport:
    outcomes: list[TurnOutcome] = []
    async with fixture_collection(settings) as scoped:
        clients = RoleClients(scoped)
        try:
            for scenario in scenarios:
                ports = ports_factory(DOCUMENT_IDS)
                history: list[HistoryRow] = []
                earlier_tool_results = ""
                for index, turn in enumerate(scenario.turns):
                    request = TurnRequest(history=history, message=turn.message, profile=PROFILE, needs_label=True, session_id=index)
                    events = [e async for e in run_turn(request, ports, scoped, clients)]
                    done = events[-1]
                    assert isinstance(done, Done)
                    history = [*history, *done.new_rows]
                    calls = [
                        (call["function"]["name"], json.loads(call["function"]["arguments"] or "{}"))
                        for row in done.new_rows
                        for call in row.tool_calls or []
                    ]
                    foreign = sum(1 for row in done.new_rows if row.role == "tool" and "not available here" in row.content)
                    cards = next((e.type for e in events if isinstance(e, Cards)), None)
                    intent = next((e.code for e in events if isinstance(e, Intent)), None)
                    current_tool_results = "\n".join(row.content for row in done.new_rows if row.role == "tool")
                    answer = next((row.content for row in reversed(done.new_rows) if row.role == "assistant" and row.content), "")
                    stale = stale_slot_mentions(earlier_tool_results, current_tool_results, answer)
                    earlier_tool_results += "\n" + current_tool_results
                    reply_language = written_language(answer)
                    card_language = next((e.language for e in events if isinstance(e, Cards)), None)
                    wanted_language = display_language(turn.expected_language)
                    language_ok = reply_language is wanted_language and card_language in (None, wanted_language)
                    tools_ok = all(any(name == want.name and _subset(want.arguments, args) for name, args in calls) for want in turn.expected_tools)
                    outcomes.append(
                        TurnOutcome(
                            scenario=scenario.id,
                            turn=index,
                            expected_intent=turn.expected_intent.value,
                            intent=intent,
                            tools=[name for name, _ in calls],
                            cards=cards,
                            foreign_tool_calls=foreign,
                            stale_slot_mentions=stale,
                            expected_language=turn.expected_language.value,
                            reply_language=reply_language.value,
                            card_language=card_language.value if card_language is not None else None,
                            passed=tools_ok and cards == turn.expected_cards and foreign == 0 and stale == 0 and language_ok,
                        )
                    )
        finally:
            await clients.aclose()
    by_scenario: dict[str, bool] = {}
    for outcome in outcomes:
        by_scenario[outcome.scenario] = by_scenario.get(outcome.scenario, True) and outcome.passed
    return ToolsReport(
        scenarios=len(scenarios),
        turns=len(outcomes),
        turn_pass_rate=sum(1 for o in outcomes if o.passed) / max(len(outcomes), 1),
        scenario_pass_rate=sum(1 for ok in by_scenario.values() if ok) / max(len(by_scenario), 1),
        language_pass_rate=sum(
            1
            for o in outcomes
            if o.reply_language == display_language(LanguageCode(o.expected_language)).value
            and o.card_language in (None, display_language(LanguageCode(o.expected_language)).value)
        )
        / max(len(outcomes), 1),
        outcomes=outcomes,
    )
