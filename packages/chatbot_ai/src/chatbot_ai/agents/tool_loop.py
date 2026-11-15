from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from openai import omit
from openai.types.chat import (
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionMessageParam,
)

from chatbot_ai.agents.base import AgentContext, AgentEvent, AgentResult
from chatbot_ai.agents.responder import agent_messages
from chatbot_ai.intents import AgentName
from chatbot_ai.interface import Cards, HistoryRow, Token, Usage
from chatbot_ai.llm import StreamedReply, StreamedToolCall, stream_reply
from chatbot_ai.settings import Role
from chatbot_ai.tools.ports import Ports
from chatbot_ai.tools.registry import (
    COMPLAINT_TOOLS,
    SCHEDULING_TOOLS,
    Tool,
    ToolOutcome,
    error_outcome,
)


def _call_param(call: StreamedToolCall) -> ChatCompletionMessageFunctionToolCallParam:
    return {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}


class ToolLoopAgent:
    def __init__(self, name: AgentName, tools: Sequence[Tool]) -> None:
        self.name = name
        self.tools = {tool.name: tool for tool in tools}

    async def _run_tool(self, call: StreamedToolCall, ports: Ports) -> ToolOutcome:
        tool = self.tools.get(call.name)
        if tool is None:
            return error_outcome(f"The tool {call.name} is not available here. Use only the tools listed now.")
        return await tool.invoke(ports, call.arguments)

    async def run(self, context: AgentContext) -> AsyncIterator[AgentEvent]:
        chat = context.clients.get(Role.chat)
        settings = context.settings
        messages: list[ChatCompletionMessageParam] = agent_messages(context, self.name)
        definitions = [tool.definition() for tool in self.tools.values()]
        rows: list[HistoryRow] = []
        cards: Cards | None = None
        usages: list[Usage] = []
        tool_timings: list[tuple[str, float]] = []
        started = context.clock()
        first_token_at: float | None = None

        for round_index in range(settings.ai_max_tool_rounds + 1):
            tools_offered = round_index < settings.ai_max_tool_rounds
            stream = await chat.stream(
                messages, max_tokens=settings.ai_chat_max_output_tokens, tools=definitions if tools_offered else omit
            )
            reply: StreamedReply | None = None
            async for item in stream_reply(stream, context.clock, started):
                if isinstance(item, Token):
                    yield item
                else:
                    reply = item
            if reply is None:
                raise RuntimeError("the chat stream ended without a reply")
            usages.append(reply.usage)
            if first_token_at is None:
                first_token_at = reply.first_token_at

            if not reply.tool_calls or not tools_offered:
                rows.append(HistoryRow(role="assistant", content=reply.text))
                break

            call_params = [_call_param(call) for call in reply.tool_calls]
            stored_calls: list[dict[str, Any]] = [dict(param) for param in call_params]  # Any: stored rows keep the OpenAI JSON shape
            rows.append(HistoryRow(role="assistant", content=reply.text, tool_calls=stored_calls))
            messages.append({"role": "assistant", "content": reply.text or None, "tool_calls": call_params})
            for call in reply.tool_calls:
                tool_started = context.clock()
                outcome = await self._run_tool(call, context.ports)
                tool_timings.append((call.name, context.clock() - tool_started))
                rows.append(HistoryRow(role="tool", content=outcome.content, tool_call_id=call.id, tool_name=call.name))
                messages.append({"role": "tool", "tool_call_id": call.id, "content": outcome.content})
                if outcome.cards is not None:
                    cards = outcome.cards

        if cards is not None and cards.items:
            yield cards
        finished = context.clock()
        yield AgentResult(
            rows=rows,
            usage=Usage(
                prompt_tokens=sum(u.prompt_tokens for u in usages),
                completion_tokens=sum(u.completion_tokens for u in usages),
            ),
            ttft=(first_token_at if first_token_at is not None else finished) - started,
            generate=finished - started,
            tool_calls=tool_timings,
        )


def scheduling_agent() -> ToolLoopAgent:
    return ToolLoopAgent(AgentName.scheduling, SCHEDULING_TOOLS)


def complaints_agent() -> ToolLoopAgent:
    return ToolLoopAgent(AgentName.complaints, COMPLAINT_TOOLS)
