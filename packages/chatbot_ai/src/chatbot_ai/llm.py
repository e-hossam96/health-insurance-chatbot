from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from openai import AsyncStream
from openai.types.chat import ChatCompletionChunk

from chatbot_ai.interface import Token, Usage


@dataclass(frozen=True)
class StreamedToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class StreamedReply:
    text: str
    tool_calls: list[StreamedToolCall]
    usage: Usage
    first_token_at: float | None


@dataclass
class _PartialCall:
    id: str = ""
    name: str = ""
    arguments: list[str] = field(default_factory=list)


async def stream_reply(
    stream: AsyncStream[ChatCompletionChunk], clock: Callable[[], float], started: float
) -> AsyncIterator[Token | StreamedReply]:
    pieces: list[str] = []
    partial: dict[int, _PartialCall] = {}
    usage = Usage()
    first_token_at: float | None = None
    async for chunk in stream:
        if chunk.usage is not None:
            usage = Usage(prompt_tokens=chunk.usage.prompt_tokens, completion_tokens=chunk.usage.completion_tokens)
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            now = clock()
            if first_token_at is None:
                first_token_at = now
            pieces.append(delta.content)
            yield Token(text=delta.content, elapsed=now - started)
        for call_delta in delta.tool_calls or []:
            call = partial.setdefault(call_delta.index, _PartialCall())
            call.id = call_delta.id or call.id
            if call_delta.function is not None:
                call.name += call_delta.function.name or ""
                call.arguments.append(call_delta.function.arguments or "")
    yield StreamedReply(
        text="".join(pieces),
        tool_calls=[
            StreamedToolCall(id=call.id or f"call_{index}", name=call.name, arguments="".join(call.arguments))
            for index, call in sorted(partial.items())
        ],
        usage=usage,
        first_token_at=first_token_at,
    )
