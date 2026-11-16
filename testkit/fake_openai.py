from __future__ import annotations

import argparse
import asyncio
import base64
import json
import struct
import threading
from collections import deque
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from testkit.embeddings import DEFAULT_DIMENSIONS, hash_embedding
from testkit.fake_brain import AUTO_TEXT, classify, scheduling_step
from testkit.live_server import serve_in_thread

JsonObject = dict[str, Any]  # Any: arbitrary JSON from the OpenAI wire format


@dataclass(frozen=True)
class ToolCallSpec:
    name: str
    arguments: JsonObject
    id: str | None = None


@dataclass(frozen=True)
class ChatReply:
    content: str | None = None
    tool_calls: tuple[ToolCallSpec, ...] = ()
    structured: JsonObject | None = None
    prompt_tokens: int = 10
    completion_tokens: int | None = None
    error_status: int | None = None
    error_message: str = ""


def text_reply(content: str, prompt_tokens: int = 10, completion_tokens: int | None = None) -> ChatReply:
    return ChatReply(content=content, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)


def tool_reply(*calls: ToolCallSpec, content: str | None = None) -> ChatReply:
    return ChatReply(content=content, tool_calls=calls)


def json_reply(structured: JsonObject) -> ChatReply:
    return ChatReply(structured=structured)


def error_reply(status: int, message: str = "fake server error") -> ChatReply:
    return ChatReply(error_status=status, error_message=message)


@dataclass(frozen=True)
class RecordedRequest:
    path: str
    body: JsonObject


class ChatCompletionBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    messages: list[JsonObject]
    stream: bool = False
    stream_options: JsonObject | None = None
    tools: list[JsonObject] | None = None
    response_format: JsonObject | None = None


class EmbeddingBody(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str
    input: str | list[str]
    dimensions: int | None = None
    encoding_format: str | None = None


class SchemaMismatch(ValueError):
    pass


def check_schema(value: object, schema: JsonObject, path: str = "$") -> None:
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaMismatch(f"{path}: {value!r} not in enum {schema['enum']}")
    expected = schema.get("type")
    checks: dict[str, type | tuple[type, ...]] = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
    }
    if isinstance(expected, str) and expected in checks and not isinstance(value, checks[expected]):
        raise SchemaMismatch(f"{path}: expected {expected}, got {type(value).__name__}")
    if isinstance(value, dict):
        properties: JsonObject = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                raise SchemaMismatch(f"{path}: missing required {key!r}")
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise SchemaMismatch(f"{path}: unexpected keys {sorted(extra)}")
        for key, item in value.items():
            if key in properties:
                check_schema(item, properties[key], f"{path}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            check_schema(item, schema["items"], f"{path}[{index}]")


def _word_pieces(text: str) -> list[str]:
    words = text.split(" ")
    return [word + (" " if index < len(words) - 1 else "") for index, word in enumerate(words)]


def _sse(payload: JsonObject) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": "fake_error", "code": None}})


def auto_reply(body: ChatCompletionBody) -> ChatReply:
    response_format = body.response_format or {}
    if response_format.get("type") == "json_schema":
        schema_name = response_format["json_schema"].get("name")
        if schema_name == "intent":
            return json_reply({"intent": classify(body.messages)})
        if schema_name == "judge":
            return json_reply({"faithful": True, "facts_present": True, "refused": False, "notes": "auto"})
        last_user = next((str(m.get("content", "")) for m in reversed(body.messages) if m.get("role") == "user"), "")
        return json_reply({"standalone": last_user, "alternates": []})
    tool_names = {str(t["function"]["name"]) for t in body.tools or []}
    text, call = scheduling_step(body.messages, tool_names) if tool_names or body.messages[-1].get("role") == "tool" else (AUTO_TEXT, None)
    if call is not None:
        return tool_reply(ToolCallSpec(call[0], call[1]))
    return text_reply(text or AUTO_TEXT)


@dataclass
class FakeOpenAI:
    embedding_dimensions: int = DEFAULT_DIMENSIONS
    auto: bool = False
    token_delay_s: float = 0.0
    requests: list[RecordedRequest] = field(default_factory=list)
    _default_queue: deque[ChatReply] = field(default_factory=deque)
    _model_queues: dict[str, deque[ChatReply]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _counter: int = 0
    base_url: str = ""

    def queue(self, *replies: ChatReply, model: str | None = None) -> None:
        with self._lock:
            target = self._default_queue if model is None else self._model_queues.setdefault(model, deque())
            target.extend(replies)

    def reset(self) -> None:
        with self._lock:
            self._default_queue.clear()
            self._model_queues.clear()
            self.requests.clear()

    def pending(self) -> int:
        with self._lock:
            return len(self._default_queue) + sum(len(q) for q in self._model_queues.values())

    @property
    def chat_requests(self) -> list[JsonObject]:
        return [r.body for r in self.requests if r.path == "/v1/chat/completions"]

    @property
    def embedding_requests(self) -> list[JsonObject]:
        return [r.body for r in self.requests if r.path == "/v1/embeddings"]

    def _next_reply(self, model: str) -> ChatReply | None:
        with self._lock:
            model_queue = self._model_queues.get(model)
            if model_queue:
                return model_queue.popleft()
            if self._default_queue:
                return self._default_queue.popleft()
            return None

    def _next_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"chatcmpl-fake-{self._counter}"

    def _record(self, path: str, body: BaseModel) -> None:
        with self._lock:
            self.requests.append(RecordedRequest(path=path, body=body.model_dump(exclude_unset=True)))

    def _message(self, reply: ChatReply, body: ChatCompletionBody) -> tuple[str | None, list[JsonObject]]:
        content = reply.content
        if reply.structured is not None:
            response_format = body.response_format or {}
            if response_format.get("type") != "json_schema":
                raise SchemaMismatch("structured reply scripted but the request did not ask for json_schema output")
            check_schema(reply.structured, response_format["json_schema"]["schema"])
            content = json.dumps(reply.structured)
        tool_calls = [
            {
                "id": call.id or f"call_{index}_{call.name}",
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for index, call in enumerate(reply.tool_calls)
        ]
        return content, tool_calls

    def _usage(self, reply: ChatReply, content: str | None, tool_calls: list[JsonObject]) -> JsonObject:
        completion = reply.completion_tokens
        if completion is None:
            completion = len((content or "").split()) + len(tool_calls)
        return {
            "prompt_tokens": reply.prompt_tokens,
            "completion_tokens": completion,
            "total_tokens": reply.prompt_tokens + completion,
        }

    def _stream(
        self, completion_id: str, body: ChatCompletionBody, content: str | None, tool_calls: list[JsonObject], usage: JsonObject
    ) -> Iterator[str]:
        def chunk(delta: JsonObject, finish_reason: str | None = None) -> JsonObject:
            return {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": 0,
                "model": body.model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            }

        yield _sse(chunk({"role": "assistant", "content": ""}))
        if content:
            for piece in _word_pieces(content):
                yield _sse(chunk({"content": piece}))
        for index, call in enumerate(tool_calls):
            yield _sse(chunk({"tool_calls": [{"index": index, "id": call["id"], "type": "function", "function": {"name": call["function"]["name"], "arguments": ""}}]}))
            arguments: str = call["function"]["arguments"]
            middle = len(arguments) // 2
            for part in (arguments[:middle], arguments[middle:]):
                if part:
                    yield _sse(chunk({"tool_calls": [{"index": index, "function": {"arguments": part}}]}))
        yield _sse(chunk({}, "tool_calls" if tool_calls else "stop"))
        if (body.stream_options or {}).get("include_usage"):
            yield _sse({"id": completion_id, "object": "chat.completion.chunk", "created": 0, "model": body.model, "choices": [], "usage": usage})
        yield "data: [DONE]\n\n"

    def build_app(self) -> FastAPI:
        app = FastAPI()

        @app.post("/v1/chat/completions", response_model=None)
        async def chat_completions(body: ChatCompletionBody) -> JSONResponse | StreamingResponse:
            self._record("/v1/chat/completions", body)
            reply = self._next_reply(body.model)
            if reply is None and self.auto:
                reply = auto_reply(body)
            if reply is None:
                return _error(500, f"no scripted reply left for model {body.model!r}")
            if reply.error_status is not None:
                return _error(reply.error_status, reply.error_message)
            try:
                content, tool_calls = self._message(reply, body)
            except SchemaMismatch as mismatch:
                return _error(400, str(mismatch))
            usage = self._usage(reply, content, tool_calls)
            completion_id = self._next_id()
            if body.stream:
                stream = self._stream(completion_id, body, content, tool_calls, usage)

                async def body_iterator() -> AsyncIterator[str]:
                    for piece in stream:
                        yield piece
                        if self.token_delay_s > 0:
                            await asyncio.sleep(self.token_delay_s)

                return StreamingResponse(body_iterator(), media_type="text/event-stream")
            message: JsonObject = {"role": "assistant", "content": content}
            if tool_calls:
                message["tool_calls"] = tool_calls
            return JSONResponse(
                {
                    "id": completion_id,
                    "object": "chat.completion",
                    "created": 0,
                    "model": body.model,
                    "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if tool_calls else "stop"}],
                    "usage": usage,
                }
            )

        @app.post("/v1/embeddings")
        async def embeddings(body: EmbeddingBody) -> JSONResponse:
            self._record("/v1/embeddings", body)
            texts = [body.input] if isinstance(body.input, str) else body.input
            dimensions = body.dimensions or self.embedding_dimensions
            data: list[JsonObject] = []
            for index, text in enumerate(texts):
                vector = hash_embedding(text, dimensions)
                encoded: list[float] | str = vector
                if body.encoding_format == "base64":
                    encoded = base64.b64encode(struct.pack(f"<{len(vector)}f", *vector)).decode("ascii")
                data.append({"object": "embedding", "index": index, "embedding": encoded})
            tokens = sum(len(text.split()) for text in texts)
            return JSONResponse(
                {"object": "list", "data": data, "model": body.model, "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}
            )

        return app


@contextmanager
def run_fake_openai(embedding_dimensions: int = DEFAULT_DIMENSIONS) -> Iterator[FakeOpenAI]:
    fake = FakeOpenAI(embedding_dimensions=embedding_dimensions)
    with serve_in_thread(fake.build_app()) as url:
        fake.base_url = f"{url}/v1"
        yield fake


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Fake OpenAI-compatible server for stack tests")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--auto", action="store_true", help="answer every request with a default reply")
    parser.add_argument("--token-delay", type=float, default=0.0, help="seconds between streamed pieces")
    parser.add_argument("--embedding-dimensions", type=int, default=DEFAULT_DIMENSIONS)
    args = parser.parse_args()
    fake = FakeOpenAI(embedding_dimensions=args.embedding_dimensions, auto=args.auto, token_delay_s=args.token_delay)
    uvicorn.run(fake.build_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
