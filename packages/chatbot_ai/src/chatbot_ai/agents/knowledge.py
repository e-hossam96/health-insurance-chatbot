from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import replace

from openai.types.chat import ChatCompletionMessageParam

from chatbot_ai.agents.base import AgentContext, AgentEvent, AgentResult
from chatbot_ai.context import to_openai_messages
from chatbot_ai.ingest.index import collection_name, embed_dense, embed_sparse
from chatbot_ai.intents import AgentName
from chatbot_ai.interface import HistoryRow, Token, Usage
from chatbot_ai.llm import StreamedReply, stream_reply
from chatbot_ai.prompts import agent_system_prompt
from chatbot_ai.rag.rewrite import rewrite_question
from chatbot_ai.rag.search import Candidate, dedupe, rrf_merge, search_one
from chatbot_ai.rerank.base import Reranker, make_reranker
from chatbot_ai.settings import AISettings, Role

NOT_FOUND_REPLY = "I couldn't find that in the documents."
SEARCH_TOOL = "search_kb"


def excerpt_block(excerpts: list[Candidate]) -> str:
    parts = [f"[{index}] {c.breadcrumb or 'Document'}\n{c.content}" for index, c in enumerate(excerpts, start=1)]
    return "Excerpts from the policy documents:\n\n" + "\n\n".join(parts)


def is_grounded(excerpts: list[Candidate], min_score: float | None) -> bool:
    if not excerpts:
        return False
    best = excerpts[0].rerank_score
    return min_score is None or best is None or best >= min_score


class KnowledgeAgent:
    name = AgentName.knowledge

    def __init__(self, reranker_factory: Callable[[AISettings], Reranker] = make_reranker) -> None:
        self._reranker_factory = reranker_factory

    async def _retrieve(self, context: AgentContext, queries: list[str], standalone: str) -> tuple[list[Candidate], dict[str, float]]:
        settings = context.settings
        clock = context.clock
        stages = {"embed": 0.0, "search": 0.0, "rerank": 0.0}
        ready = await context.ports.knowledge.ready_document_ids()
        qdrant = context.clients.qdrant()
        collection = collection_name(settings)
        if not ready or not await qdrant.collection_exists(collection):
            return [], stages

        started = clock()
        embedder = context.clients.get(Role.embedding)
        with context.tracer.stage("embed", "embedding", model=embedder.model):
            dense = await embed_dense(embedder, queries, "query", settings)
            sparse = embed_sparse(queries, "query")
        embedded = clock()
        with context.tracer.stage("search", "retriever"):
            ranked_lists = [
                await search_one(qdrant, collection, d, s, settings.ai_retrieval_mode, settings.ai_prefetch_k, ready)
                for d, s in zip(dense, sparse, strict=True)
            ]
            candidates = dedupe(rrf_merge(ranked_lists, settings.ai_fused_k))
        searched = clock()
        with context.tracer.stage("rerank"):
            reranked = await self._reranker_factory(settings).rerank(standalone, [c.content for c in candidates], settings.ai_context_k)
        excerpts = [replace(candidates[r.index], rerank_score=r.score) for r in reranked]
        stages.update(embed=embedded - started, search=searched - embedded, rerank=clock() - searched)
        return excerpts, stages

    async def run(self, context: AgentContext) -> AsyncIterator[AgentEvent]:
        settings = context.settings
        request = context.request
        clock = context.clock
        started = clock()
        rewriter = context.clients.get(Role.rewrite)
        with context.tracer.stage("rewrite", "generation", model=rewriter.model):
            rewrite = await rewrite_question(
                rewriter, request.history, request.message, settings.ai_query_count, settings.ai_rewrite_max_output_tokens
            )
        rewritten = clock()
        excerpts, stages = await self._retrieve(context, rewrite.queries, rewrite.standalone)
        stages["rewrite"] = rewritten - started

        call_id = f"call_{SEARCH_TOOL}_{uuid.uuid4().hex[:12]}"
        rows = [
            HistoryRow(
                role="assistant",
                content="",
                tool_calls=[{"id": call_id, "type": "function", "function": {"name": SEARCH_TOOL, "arguments": json.dumps({"query": rewrite.standalone})}}],
            ),
            HistoryRow(
                role="tool",
                content=json.dumps({"excerpts": [{"section": c.breadcrumb, "content": c.content} for c in excerpts]}, ensure_ascii=False),
                tool_call_id=call_id,
                tool_name=SEARCH_TOOL,
            ),
        ]

        generation_started = clock()
        if not is_grounded(excerpts, settings.ai_rerank_min_score):
            yield Token(text=NOT_FOUND_REPLY, elapsed=0.0)
            finished = clock()
            yield AgentResult(
                rows=[*rows, HistoryRow(role="assistant", content=NOT_FOUND_REPLY)],
                usage=rewrite.usage,
                ttft=0.0,
                generate=finished - generation_started,
                stages=stages,
            )
            return

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": agent_system_prompt(self.name, request.profile) + "\n\n" + excerpt_block(excerpts)},
            *to_openai_messages(request.history),
            {"role": "user", "content": request.message},
        ]
        chat = context.clients.get(Role.chat)
        reply: StreamedReply | None = None
        with context.tracer.stage("generate", "generation", model=chat.model):
            stream = await chat.stream(messages, max_tokens=settings.ai_chat_max_output_tokens)
            async for item in stream_reply(stream, clock, generation_started):
                if isinstance(item, Token):
                    yield item
                else:
                    reply = item
        if reply is None:
            raise RuntimeError("the chat stream ended without a reply")
        finished = clock()
        yield AgentResult(
            rows=[*rows, HistoryRow(role="assistant", content=reply.text)],
            usage=Usage(
                prompt_tokens=rewrite.usage.prompt_tokens + reply.usage.prompt_tokens,
                completion_tokens=rewrite.usage.completion_tokens + reply.usage.completion_tokens,
            ),
            ttft=(reply.first_token_at if reply.first_token_at is not None else finished) - generation_started,
            generate=finished - generation_started,
            stages=stages,
        )
