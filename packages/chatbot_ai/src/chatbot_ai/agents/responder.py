from __future__ import annotations

from collections.abc import AsyncIterator

from openai.types.chat import ChatCompletionMessageParam

from chatbot_ai.agents.base import AgentContext, AgentEvent, AgentResult
from chatbot_ai.context import to_openai_messages
from chatbot_ai.intents import AgentName
from chatbot_ai.interface import HistoryRow, Token, Usage
from chatbot_ai.prompts import agent_system_prompt
from chatbot_ai.settings import Role


def agent_messages(context: AgentContext, agent: AgentName) -> list[ChatCompletionMessageParam]:
    request = context.request
    return [
        {"role": "system", "content": agent_system_prompt(agent, request.profile)},
        *to_openai_messages(request.history),
        {"role": "user", "content": request.message},
    ]


class ResponderAgent:
    name = AgentName.responder

    async def run(self, context: AgentContext) -> AsyncIterator[AgentEvent]:
        chat = context.clients.get(Role.chat)
        started = context.clock()
        first_token_at: float | None = None
        pieces: list[str] = []
        usage = Usage()
        stream = await chat.stream(agent_messages(context, self.name), max_tokens=context.settings.ai_chat_max_output_tokens)
        async for chunk in stream:
            if chunk.usage is not None:
                usage = Usage(prompt_tokens=chunk.usage.prompt_tokens, completion_tokens=chunk.usage.completion_tokens)
            if not chunk.choices:
                continue
            text = chunk.choices[0].delta.content
            if text:
                now = context.clock()
                if first_token_at is None:
                    first_token_at = now
                pieces.append(text)
                yield Token(text=text, elapsed=now - started)
        finished = context.clock()
        yield AgentResult(
            rows=[HistoryRow(role="assistant", content="".join(pieces))],
            usage=usage,
            ttft=(first_token_at if first_token_at is not None else finished) - started,
            generate=finished - started,
        )
