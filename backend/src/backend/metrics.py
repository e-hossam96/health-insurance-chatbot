import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Literal, get_args

from fastapi import HTTPException
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
)

TurnOutcome = Literal["ok", "error", "cancelled"]
Stage = Literal["classify", "rewrite", "embed", "search", "rerank", "generate"]
RateLimit = Literal["chat_minute", "chat_daily", "message_length", "signup", "login"]
CardAction = Literal["book", "cancel", "complaint"]
CardOutcome = Literal["ok", "conflict", "rejected", "error"]
IngestOutcome = Literal["ok", "failed"]
TokenKind = Literal["prompt", "completion"]
STAGES: tuple[Stage, ...] = ("classify", "rewrite", "embed", "search", "rerank", "generate")
LLM_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0)
GAP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)

chat_turns_total = Counter("chat_turns_total", "Chat turns by outcome", ["outcome"])
chat_turns_by_agent_total = Counter("chat_turns_by_agent_total", "Completed chat turns by the agent that answered", ["agent"])
chat_ttft_seconds = Histogram("chat_ttft_seconds", "Time to first token of the answer", buckets=LLM_BUCKETS)
chat_llm_duration_seconds = Histogram("chat_llm_duration_seconds", "Duration of the answering LLM work", buckets=LLM_BUCKETS)
chat_turn_duration_seconds = Histogram("chat_turn_duration_seconds", "Total duration of a completed turn", buckets=LLM_BUCKETS)
chat_chunk_gap_seconds = Histogram("chat_chunk_gap_seconds", "Gap between streamed tokens", buckets=GAP_BUCKETS)
chat_tokens_total = Counter("chat_tokens_total", "LLM tokens used by chat turns", ["kind"])
chat_stage_duration_seconds = Histogram("chat_stage_duration_seconds", "Duration of each turn stage", ["stage"], buckets=LLM_BUCKETS)
kb_ingest_total = Counter("kb_ingest_total", "KB ingestion jobs by outcome", ["outcome"])
kb_ingest_duration_seconds = Histogram("kb_ingest_duration_seconds", "KB ingestion job duration", buckets=(1, 2, 5, 10, 30, 60, 120, 300, 600))
kb_documents_processing = Gauge("kb_documents_processing", "KB documents currently in processing")
rate_limit_rejections_total = Counter("rate_limit_rejections_total", "Requests rejected by an abuse limit", ["limit"])
signups_total = Counter("signups_total", "Accounts created through sign-up")
card_actions_total = Counter("card_actions_total", "Card actions by action and outcome", ["action", "outcome"])


# A series born at its first increment has no zero sample, so increase() misses that first event.
def _expose_fixed_label_series_at_zero() -> None:
    for action in get_args(CardAction):
        for card_outcome in get_args(CardOutcome):
            card_actions_total.labels(action=action, outcome=card_outcome)
    for turn_outcome in get_args(TurnOutcome):
        chat_turns_total.labels(outcome=turn_outcome)
    for ingest_outcome in get_args(IngestOutcome):
        kb_ingest_total.labels(outcome=ingest_outcome)
    for limit in get_args(RateLimit):
        rate_limit_rejections_total.labels(limit=limit)
    for kind in get_args(TokenKind):
        chat_tokens_total.labels(kind=kind)


_expose_fixed_label_series_at_zero()


def record_turn_outcome(outcome: TurnOutcome) -> None:
    chat_turns_total.labels(outcome=outcome).inc()


def record_completed_turn(agent: str, ttft: float, generate: float, total: float, stages: dict[Stage, float], prompt_tokens: int, completion_tokens: int) -> None:
    chat_turns_by_agent_total.labels(agent=agent or "unknown").inc()
    chat_ttft_seconds.observe(ttft)
    chat_llm_duration_seconds.observe(generate)
    chat_turn_duration_seconds.observe(total)
    for stage, seconds in stages.items():
        if seconds > 0:
            chat_stage_duration_seconds.labels(stage=stage).observe(seconds)
    chat_tokens_total.labels(kind="prompt").inc(prompt_tokens)
    chat_tokens_total.labels(kind="completion").inc(completion_tokens)


def record_rate_limit(limit: RateLimit) -> None:
    rate_limit_rejections_total.labels(limit=limit).inc()


def card_action(action: CardAction) -> Callable[[], AsyncIterator[None]]:
    async def track() -> AsyncIterator[None]:
        outcome: CardOutcome = "ok"
        try:
            yield
        except HTTPException as error:
            outcome = "conflict" if error.status_code == 409 else "rejected" if error.status_code < 500 else "error"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            card_actions_total.labels(action=action, outcome=outcome).inc()

    return track


UNMATCHED_ROUTE = "unmatched"


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    return template if isinstance(template, str) else UNMATCHED_ROUTE


async def prometheus_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.url.path == "/metrics":
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    route = _route_template(request)

    http_requests_total.labels(
        method=request.method,
        route=route,
        status=response.status_code,
    ).inc()
    http_request_duration_seconds.labels(
        method=request.method,
        route=route,
    ).observe(elapsed)

    return response
