from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import OpenAIError
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema

from chatbot_ai.clients import RoleClient
from chatbot_ai.intents import IntentCode
from chatbot_ai.interface import HistoryRow, Usage
from chatbot_ai.prompts import load_prompt

logger = logging.getLogger(__name__)

ROUTER_MAX_OUTPUT_TOKENS = 20

INTENT_RESPONSE_FORMAT: ResponseFormatJSONSchema = {
    "type": "json_schema",
    "json_schema": {
        "name": "intent",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"intent": {"type": "string", "enum": [code.value for code in IntentCode]}},
            "required": ["intent"],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class Classification:
    intent: IntentCode | None
    usage: Usage


def router_window(history: list[HistoryRow], size: int) -> list[HistoryRow]:
    window = history[-size:]
    for index, row in enumerate(window):
        if row.role == "user":
            return window[index:]
    return []


def router_messages(history: list[HistoryRow], message: str, window_size: int) -> list[ChatCompletionMessageParam]:
    messages: list[ChatCompletionMessageParam] = [{"role": "system", "content": load_prompt("router")}]
    for row in router_window(history, window_size):
        if row.role == "user":
            messages.append({"role": "user", "content": row.content})
        elif row.role == "assistant" and row.content and not row.tool_calls:
            messages.append({"role": "assistant", "content": row.content})
    messages.append({"role": "user", "content": message})
    return messages


async def classify(router: RoleClient, history: list[HistoryRow], message: str, window_size: int) -> Classification:
    try:
        completion = await router.complete(
            router_messages(history, message, window_size),
            max_tokens=ROUTER_MAX_OUTPUT_TOKENS,
            response_format=INTENT_RESPONSE_FORMAT,
        )
    except OpenAIError:
        logger.warning("router call failed; falling back to the responder", exc_info=True)
        return Classification(intent=None, usage=Usage())
    usage = Usage(
        prompt_tokens=completion.usage.prompt_tokens if completion.usage else 0,
        completion_tokens=completion.usage.completion_tokens if completion.usage else 0,
    )
    content = completion.choices[0].message.content if completion.choices else None
    try:
        intent = IntentCode(json.loads(content or "")["intent"])
    except (ValueError, KeyError, TypeError):
        logger.warning("router returned an unusable classification: %r", content)
        return Classification(intent=None, usage=usage)
    return Classification(intent=intent, usage=usage)
