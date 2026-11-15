from __future__ import annotations

from collections.abc import AsyncIterator

from openai.types.chat import ChatCompletionMessageParam

from chatbot_ai.agents.base import AgentContext, AgentEvent, AgentResult
from chatbot_ai.context import to_openai_messages
from chatbot_ai.intents import AgentName
from chatbot_ai.interface import HistoryRow, Token
from chatbot_ai.llm import StreamedReply, stream_reply
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
        stream = await chat.stream(agent_messages(context, self.name), max_tokens=context.settings.ai_chat_max_output_tokens)
        reply: StreamedReply | None = None
        async for item in stream_reply(stream, context.clock, started):
            if isinstance(item, Token):
                yield item
            else:
                reply = item
        finished = context.clock()
        if reply is None:
            raise RuntimeError("the chat stream ended without a reply")
        yield AgentResult(
            rows=[HistoryRow(role="assistant", content=reply.text)],
            usage=reply.usage,
            ttft=(reply.first_token_at if reply.first_token_at is not None else finished) - started,
            generate=finished - started,
        )
