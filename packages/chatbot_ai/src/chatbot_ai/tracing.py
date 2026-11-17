from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import TYPE_CHECKING, Literal, Protocol

from chatbot_ai.interface import Usage

if TYPE_CHECKING:
    from langfuse import Langfuse, LangfuseGeneration
    from langfuse._client.span import LangfuseObservationWrapper

SpanKind = Literal["span", "generation", "tool", "retriever", "embedding", "agent", "chain"]
TRACE_NAME = "chat turn"


def langfuse_session_id(chat_session_id: int) -> str:
    return f"chat-{chat_session_id}"


def usage_details(usage: Usage) -> dict[str, int]:
    return {"input": usage.prompt_tokens, "output": usage.completion_tokens}


class StageRecorder(Protocol):
    def record(self, *, input: object = None, output: object = None, usage: Usage | None = None) -> None: ...


class NoopRecorder:
    def record(self, *, input: object = None, output: object = None, usage: Usage | None = None) -> None:
        return None


class TurnTracer(Protocol):
    def turn(self, chat_session_id: int) -> AbstractContextManager[StageRecorder]: ...

    def stage(self, name: str, kind: SpanKind = "span", model: str | None = None) -> AbstractContextManager[StageRecorder]: ...

    def flush(self) -> None: ...


class NoopTracer:
    def turn(self, chat_session_id: int) -> AbstractContextManager[StageRecorder]:
        return nullcontext(NoopRecorder())

    def stage(self, name: str, kind: SpanKind = "span", model: str | None = None) -> AbstractContextManager[StageRecorder]:
        return nullcontext(NoopRecorder())

    def flush(self) -> None:
        return None


class LangfuseRecorder:
    def __init__(self, observation: LangfuseObservationWrapper) -> None:
        self._observation = observation

    def record(self, *, input: object = None, output: object = None, usage: Usage | None = None) -> None:
        self._observation.update(input=input, output=output, usage_details=usage_details(usage) if usage is not None else None)


class LangfuseTracer:
    def __init__(self, client: Langfuse) -> None:
        self._client = client

    @contextmanager
    def turn(self, chat_session_id: int) -> Iterator[StageRecorder]:
        from langfuse import propagate_attributes
        from opentelemetry import context as otel_context

        # FastAPI's own OpenTelemetry request span is not exported to Langfuse, so the turn must start a fresh trace
        detached = otel_context.attach(otel_context.Context())
        try:
            with (
                propagate_attributes(session_id=langfuse_session_id(chat_session_id), trace_name=TRACE_NAME),
                self._client.start_as_current_observation(name=TRACE_NAME, as_type="agent") as observation,
            ):
                yield LangfuseRecorder(observation)
        finally:
            otel_context.detach(detached)

    @contextmanager
    def stage(self, name: str, kind: SpanKind = "span", model: str | None = None) -> Iterator[StageRecorder]:
        if kind == "generation":
            generation: LangfuseGeneration
            with self._client.start_as_current_observation(name=name, as_type="generation", model=model) as generation:
                yield LangfuseRecorder(generation)
        else:
            with self._client.start_as_current_observation(name=name, as_type=kind) as observation:
                yield LangfuseRecorder(observation)

    def flush(self) -> None:
        self._client.flush()


def make_tracer(public_key: str | None, secret_key: str | None, host: str | None) -> TurnTracer:
    if not public_key or not secret_key:
        return NoopTracer()
    from langfuse import Langfuse

    return LangfuseTracer(Langfuse(public_key=public_key, secret_key=secret_key, host=host or None))
