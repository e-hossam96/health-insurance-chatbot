from __future__ import annotations

import json

import openai
import pytest
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from testkit.embeddings import cosine, hash_embedding
from testkit.fake_openai import (
    FakeOpenAI,
    SchemaMismatch,
    ToolCallSpec,
    check_schema,
    error_reply,
    json_reply,
    text_reply,
    tool_reply,
)

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["visit.book", "qa.kb", "other"]},
        "language": {"type": "string", "enum": ["ar", "en", "other"]},
    },
    "required": ["intent"],
    "additionalProperties": False,
}
USER_MESSAGE: list[ChatCompletionMessageParam] = [{"role": "user", "content": "hi"}]


@pytest.mark.anyio()
async def test_text_completion_returns_content_and_usage(fake_openai: FakeOpenAI, openai_client: AsyncOpenAI) -> None:
    fake_openai.queue(text_reply("Hello there friend", prompt_tokens=7))
    result = await openai_client.chat.completions.create(model="chat-model", messages=USER_MESSAGE)
    assert result.choices[0].message.content == "Hello there friend"
    assert result.choices[0].finish_reason == "stop"
    assert result.usage is not None
    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (7, 3)
    assert fake_openai.chat_requests[0]["messages"] == USER_MESSAGE


@pytest.mark.anyio()
async def test_streaming_text_arrives_in_pieces_with_usage_last(
    fake_openai: FakeOpenAI, openai_client: AsyncOpenAI
) -> None:
    fake_openai.queue(text_reply("one two three four", completion_tokens=4))
    stream = await openai_client.chat.completions.create(
        model="chat-model",
        messages=USER_MESSAGE,
        stream=True,
        stream_options={"include_usage": True},
    )
    pieces: list[str] = []
    usage_chunks = 0
    finish_reasons: list[str] = []
    async for chunk in stream:
        if chunk.usage is not None:
            usage_chunks += 1
            assert chunk.choices == []
            assert chunk.usage.completion_tokens == 4
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            pieces.append(delta.content)
        if chunk.choices[0].finish_reason:
            finish_reasons.append(chunk.choices[0].finish_reason)
    assert pieces == ["one ", "two ", "three ", "four"]
    assert finish_reasons == ["stop"]
    assert usage_chunks == 1


@pytest.mark.anyio()
async def test_stream_without_include_usage_has_no_usage_chunk(
    fake_openai: FakeOpenAI, openai_client: AsyncOpenAI
) -> None:
    fake_openai.queue(text_reply("short"))
    stream = await openai_client.chat.completions.create(model="m", messages=USER_MESSAGE, stream=True)
    assert all([chunk.usage is None async for chunk in stream])


@pytest.mark.anyio()
async def test_tool_calls_non_streaming(fake_openai: FakeOpenAI, openai_client: AsyncOpenAI) -> None:
    fake_openai.queue(tool_reply(ToolCallSpec("get_availability", {"doctor_id": 3}, id="call_a")))
    tools: list[ChatCompletionToolParam] = [
        {"type": "function", "function": {"name": "get_availability", "parameters": {"type": "object"}}}
    ]
    result = await openai_client.chat.completions.create(model="m", messages=USER_MESSAGE, tools=tools)
    message = result.choices[0].message
    assert result.choices[0].finish_reason == "tool_calls"
    assert message.tool_calls is not None
    call = message.tool_calls[0]
    assert call.id == "call_a"
    assert call.type == "function"
    assert call.function.name == "get_availability"
    assert json.loads(call.function.arguments) == {"doctor_id": 3}
    assert fake_openai.chat_requests[0]["tools"] == tools


@pytest.mark.anyio()
async def test_tool_calls_streaming_accumulate_from_deltas(fake_openai: FakeOpenAI, openai_client: AsyncOpenAI) -> None:
    fake_openai.queue(
        tool_reply(
            ToolCallSpec("list_specialties", {}),
            ToolCallSpec("search_doctors", {"specialty_id": 1, "location_id": 2}),
        )
    )
    stream = await openai_client.chat.completions.create(model="m", messages=USER_MESSAGE, stream=True)
    calls: dict[int, dict[str, str]] = {}
    finish = None
    async for chunk in stream:
        choice = chunk.choices[0]
        finish = choice.finish_reason or finish
        for delta in choice.delta.tool_calls or []:
            entry = calls.setdefault(delta.index, {"id": "", "name": "", "arguments": ""})
            entry["id"] = delta.id or entry["id"]
            if delta.function is not None:
                entry["name"] += delta.function.name or ""
                entry["arguments"] += delta.function.arguments or ""
    assert finish == "tool_calls"
    assert [c["name"] for c in calls.values()] == ["list_specialties", "search_doctors"]
    assert json.loads(calls[1]["arguments"]) == {"specialty_id": 1, "location_id": 2}
    assert all(c["id"] for c in calls.values())


@pytest.mark.anyio()
async def test_structured_output_follows_the_requested_schema(fake_openai: FakeOpenAI, openai_client: AsyncOpenAI) -> None:
    fake_openai.queue(json_reply({"intent": "visit.book"}))
    result = await openai_client.chat.completions.create(
        model="router",
        messages=USER_MESSAGE,
        response_format={"type": "json_schema", "json_schema": {"name": "intent", "schema": INTENT_SCHEMA, "strict": True}},
    )
    content = result.choices[0].message.content
    assert content is not None
    assert json.loads(content) == {"intent": "visit.book"}


@pytest.mark.anyio()
async def test_structured_reply_without_json_schema_request_is_rejected(
    fake_openai: FakeOpenAI, openai_client: AsyncOpenAI
) -> None:
    fake_openai.queue(json_reply({"intent": "visit.book"}))
    with pytest.raises(openai.BadRequestError, match="json_schema"):
        await openai_client.chat.completions.create(model="router", messages=USER_MESSAGE)


@pytest.mark.anyio()
async def test_structured_reply_that_breaks_the_schema_is_rejected(
    fake_openai: FakeOpenAI, openai_client: AsyncOpenAI
) -> None:
    fake_openai.queue(json_reply({"intent": "visit.unknown"}))
    with pytest.raises(openai.BadRequestError, match="enum"):
        await openai_client.chat.completions.create(
            model="router",
            messages=USER_MESSAGE,
            response_format={"type": "json_schema", "json_schema": {"name": "intent", "schema": INTENT_SCHEMA, "strict": True}},
        )


def test_schema_checker_covers_types_required_and_extra_keys() -> None:
    schema = {
        "type": "object",
        "properties": {"standalone": {"type": "string"}, "alternates": {"type": "array", "items": {"type": "string"}}},
        "required": ["standalone", "alternates"],
        "additionalProperties": False,
    }
    check_schema({"standalone": "q", "alternates": ["a", "b"]}, schema)
    for bad, message in (
        ({"standalone": "q"}, "missing required"),
        ({"standalone": "q", "alternates": [1]}, "expected string"),
        ({"standalone": "q", "alternates": [], "extra": 1}, "unexpected keys"),
    ):
        with pytest.raises(SchemaMismatch, match=message):
            check_schema(bad, schema)


@pytest.mark.anyio()
async def test_replies_can_be_queued_per_model(fake_openai: FakeOpenAI, openai_client: AsyncOpenAI) -> None:
    fake_openai.queue(text_reply("from chat"))
    fake_openai.queue(text_reply("from router"), model="router")
    chat = await openai_client.chat.completions.create(model="chat", messages=USER_MESSAGE)
    router = await openai_client.chat.completions.create(model="router", messages=USER_MESSAGE)
    assert chat.choices[0].message.content == "from chat"
    assert router.choices[0].message.content == "from router"
    assert fake_openai.pending() == 0


@pytest.mark.anyio()
async def test_scripted_error_and_missing_script_raise(fake_openai: FakeOpenAI, openai_client: AsyncOpenAI) -> None:
    fake_openai.queue(error_reply(503, "overloaded"))
    with pytest.raises(openai.APIStatusError) as overloaded:
        await openai_client.chat.completions.create(model="m", messages=USER_MESSAGE)
    assert overloaded.value.status_code == 503
    with pytest.raises(openai.InternalServerError, match="no scripted reply"):
        await openai_client.chat.completions.create(model="m", messages=USER_MESSAGE)


@pytest.mark.anyio()
async def test_embeddings_are_deterministic_hash_vectors(fake_openai: FakeOpenAI, openai_client: AsyncOpenAI) -> None:
    texts = ["dental cleaning limit", "dental cleaning yearly limit", "appeal a rejected claim"]
    result = await openai_client.embeddings.create(model="embed", input=texts, dimensions=32)
    vectors = [item.embedding for item in result.data]
    assert [len(v) for v in vectors] == [32, 32, 32]
    for text, vector in zip(texts, vectors, strict=True):
        assert vector == pytest.approx(hash_embedding(text, 32), abs=1e-6)
    assert cosine(vectors[0], vectors[1]) > cosine(vectors[0], vectors[2])
    assert fake_openai.embedding_requests[0]["dimensions"] == 32

    float_result = await openai_client.embeddings.create(model="embed", input="dental cleaning limit", dimensions=32, encoding_format="float")
    assert float_result.data[0].embedding == pytest.approx(vectors[0], abs=1e-6)


def test_hash_embedding_is_unit_length_and_stable() -> None:
    first = hash_embedding("Outpatient co-pay is 50 EGP", 64)
    assert first == hash_embedding("Outpatient co-pay is 50 EGP", 64)
    assert sum(v * v for v in first) == pytest.approx(1.0)
    assert hash_embedding("", 8) == [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


@pytest.mark.anyio()
async def test_auto_mode_answers_router_rewrite_and_chat_without_a_script(fake_openai: FakeOpenAI, openai_client: AsyncOpenAI) -> None:
    fake_openai.auto = True
    try:
        router = await openai_client.chat.completions.create(
            model="router",
            messages=USER_MESSAGE,
            response_format={"type": "json_schema", "json_schema": {"name": "intent", "schema": INTENT_SCHEMA, "strict": True}},
        )
        assert json.loads(router.choices[0].message.content or "") == {"intent": "other", "language": "en"}
        arabic = await openai_client.chat.completions.create(
            model="router",
            messages=[{"role": "user", "content": "مرحبا"}],
            response_format={"type": "json_schema", "json_schema": {"name": "intent", "schema": INTENT_SCHEMA, "strict": True}},
        )
        assert json.loads(arabic.choices[0].message.content or "") == {"intent": "other", "language": "ar"}
        chat = await openai_client.chat.completions.create(model="chat", messages=USER_MESSAGE)
        assert chat.choices[0].message.content == "Streaming check: one two three four five six."
    finally:
        fake_openai.auto = False
