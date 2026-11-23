from __future__ import annotations

from collections.abc import AsyncIterator

from openai.types.chat import ChatCompletionMessageParam

from chatbot_ai.agents.base import AgentContext, AgentEvent, AgentResult
from chatbot_ai.context import to_openai_messages
from chatbot_ai.intents import AgentName
from chatbot_ai.interface import HistoryRow, Token
from chatbot_ai.llm import StreamedReply, reply_output, stream_reply
from chatbot_ai.prompts import agent_system_prompt, language_reminder
from chatbot_ai.settings import Role


def agent_messages(context: AgentContext, agent: AgentName) -> list[ChatCompletionMessageParam]:
    request = context.request
    return [
        {"role": "system", "content": agent_system_prompt(agent, request.profile, context.language)},
        *to_openai_messages(request.history),
        {"role": "user", "content": request.message},
        *language_reminder(context.language),
    ]


class ResponderAgent:
    name = AgentName.responder

    async def run(self, context: AgentContext) -> AsyncIterator[AgentEvent]:
        chat = context.clients.get(Role.chat)
        started = context.clock()
        reply: StreamedReply | None = None
        messages = agent_messages(context, self.name)
        with context.tracer.stage("generate", "generation", model=chat.model) as generate_record:
            stream = await chat.stream(messages, max_tokens=context.settings.ai_chat_max_output_tokens)
            async for item in stream_reply(stream, context.clock, started):
                if isinstance(item, Token):
                    yield item
                else:
                    reply = item
            if reply is not None:
                generate_record.record(input=messages, output=reply_output(reply), usage=reply.usage)
        finished = context.clock()
        if reply is None:
            raise RuntimeError("the chat stream ended without a reply")
        yield AgentResult(
            rows=[HistoryRow(role="assistant", content=reply.text)],
            usage=reply.usage,
            ttft=(reply.first_token_at if reply.first_token_at is not None else finished) - started,
            generate=finished - started,
        )
