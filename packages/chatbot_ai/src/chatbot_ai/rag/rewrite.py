from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import OpenAIError
from openai.types.chat import ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema

from chatbot_ai.clients import RoleClient
from chatbot_ai.interface import HistoryRow, Usage
from chatbot_ai.prompts import load_prompt
from chatbot_ai.router import router_window

logger = logging.getLogger(__name__)
REWRITE_HISTORY_ROWS = 6


@dataclass(frozen=True)
class Rewrite:
    standalone: str
    alternates: list[str]
    usage: Usage
    fell_back: bool = False

    @property
    def queries(self) -> list[str]:
        return [self.standalone, *self.alternates]


def rewrite_format(query_count: int) -> ResponseFormatJSONSchema:
    properties: dict[str, object] = {"standalone": {"type": "string"}}
    required = ["standalone"]
    if query_count > 1:
        properties["alternates"] = {"type": "array", "items": {"type": "string"}}
        required.append("alternates")
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "rewrite",
            "strict": True,
            "schema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
        },
    }


def rewrite_messages(history: list[HistoryRow], message: str, query_count: int) -> list[ChatCompletionMessageParam]:
    instructions = load_prompt("rewrite").format(alternate_count=query_count - 1)
    transcript = "\n".join(
        f"{row.role}: {row.content}"
        for row in router_window(history, REWRITE_HISTORY_ROWS)
        if row.role in ("user", "assistant") and row.content and not row.tool_calls
    )
    return [
        {"role": "system", "content": instructions},
        {"role": "user", "content": f"Conversation so far:\n{transcript or '(none)'}\n\nLatest question: {message}"},
    ]


async def rewrite_question(
    rewriter: RoleClient, history: list[HistoryRow], message: str, query_count: int, max_tokens: int = 1024
) -> Rewrite:
    try:
        completion = await rewriter.complete(
            rewrite_messages(history, message, query_count),
            max_tokens=max_tokens,
            response_format=rewrite_format(query_count),
        )
        content = completion.choices[0].message.content if completion.choices else None
        parsed = json.loads(content or "")
        standalone = str(parsed["standalone"]).strip() or message
        alternates = [str(a).strip() for a in parsed.get("alternates", []) if str(a).strip()][: query_count - 1]
        usage = Usage(
            prompt_tokens=completion.usage.prompt_tokens if completion.usage else 0,
            completion_tokens=completion.usage.completion_tokens if completion.usage else 0,
        )
        return Rewrite(standalone=standalone, alternates=alternates, usage=usage)
    except (OpenAIError, ValueError, KeyError, TypeError):
        logger.warning("query rewrite failed; searching with the raw message", exc_info=True)
        return Rewrite(standalone=message, alternates=[], usage=Usage(), fell_back=True)
