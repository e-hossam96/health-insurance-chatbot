from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from langfuse import Langfuse

SpanKind = Literal["span", "generation", "tool", "retriever", "embedding", "agent", "chain"]
TRACE_NAME = "chat turn"


def langfuse_session_id(chat_session_id: int) -> str:
    return f"chat-{chat_session_id}"


class TurnTracer(Protocol):
    def turn(self, chat_session_id: int) -> AbstractContextManager[None]: ...

    def stage(self, name: str, kind: SpanKind = "span", model: str | None = None) -> AbstractContextManager[None]: ...

    def flush(self) -> None: ...


class NoopTracer:
    def turn(self, chat_session_id: int) -> AbstractContextManager[None]:
        return nullcontext()

    def stage(self, name: str, kind: SpanKind = "span", model: str | None = None) -> AbstractContextManager[None]:
        return nullcontext()

    def flush(self) -> None:
        return None


class LangfuseTracer:
    def __init__(self, client: Langfuse) -> None:
        self._client = client

    @contextmanager
    def turn(self, chat_session_id: int) -> Iterator[None]:
        from langfuse import propagate_attributes

        with (
            propagate_attributes(session_id=langfuse_session_id(chat_session_id), trace_name=TRACE_NAME),
            self._client.start_as_current_observation(name=TRACE_NAME, as_type="agent"),
        ):
            yield

    @contextmanager
    def stage(self, name: str, kind: SpanKind = "span", model: str | None = None) -> Iterator[None]:
        if kind == "generation":
            with self._client.start_as_current_observation(name=name, as_type="generation", model=model):
                yield
        else:
            with self._client.start_as_current_observation(name=name, as_type=kind):
                yield

    def flush(self) -> None:
        self._client.flush()


def make_tracer(public_key: str | None, secret_key: str | None, host: str | None) -> TurnTracer:
    if not public_key or not secret_key:
        return NoopTracer()
    from langfuse import Langfuse

    return LangfuseTracer(Langfuse(public_key=public_key, secret_key=secret_key, host=host or None))
