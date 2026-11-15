from __future__ import annotations

import time
from collections.abc import AsyncIterator, Mapping

from chatbot_ai.agents.base import (
    Agent,
    AgentContext,
    AgentNotAvailable,
    AgentResult,
    Clock,
)
from chatbot_ai.agents.responder import ResponderAgent
from chatbot_ai.agents.tool_loop import complaints_agent, scheduling_agent
from chatbot_ai.clients import RoleClients
from chatbot_ai.intents import AgentName, agent_for
from chatbot_ai.interface import (
    Done,
    HistoryRow,
    Intent,
    Ports,
    Timings,
    TurnEvent,
    TurnRequest,
    Usage,
)
from chatbot_ai.router import classify
from chatbot_ai.settings import AISettings, Role


def default_agents() -> dict[AgentName, Agent]:
    return {
        AgentName.scheduling: scheduling_agent(),
        AgentName.complaints: complaints_agent(),
        AgentName.responder: ResponderAgent(),
    }


def _sum_usage(*usages: Usage) -> Usage:
    return Usage(
        prompt_tokens=sum(u.prompt_tokens for u in usages),
        completion_tokens=sum(u.completion_tokens for u in usages),
    )


async def run_turn(
    req: TurnRequest,
    ports: Ports,
    settings: AISettings,
    clients: RoleClients | None = None,
    agents: Mapping[AgentName, Agent] | None = None,
    clock: Clock = time.monotonic,
) -> AsyncIterator[TurnEvent]:
    own_clients = clients is None
    role_clients = clients if clients is not None else RoleClients(settings)
    registry = agents if agents is not None else default_agents()
    try:
        started = clock()
        classification = await classify(
            role_clients.get(Role.router), req.history, req.message, settings.ai_router_history_rows
        )
        classified = clock()
        if req.needs_label and classification.intent is not None:
            yield Intent(code=classification.intent.value)

        agent_name = agent_for(classification.intent)
        agent = registry.get(agent_name)
        if agent is None:
            raise AgentNotAvailable(f"no {agent_name.value} agent is registered")

        context = AgentContext(request=req, ports=ports, settings=settings, clients=role_clients, clock=clock)
        result: AgentResult | None = None
        async for event in agent.run(context):
            if isinstance(event, AgentResult):
                result = event
            else:
                yield event
        if result is None:
            raise RuntimeError(f"{agent_name.value} agent finished without a result")

        yield Done(
            new_rows=[HistoryRow(role="user", content=req.message), *result.rows],
            timings=Timings(
                classify=classified - started,
                ttft=result.ttft,
                generate=result.generate,
                total=clock() - started,
                tool_calls=result.tool_calls,
            ),
            usage=_sum_usage(classification.usage, result.usage),
        )
    finally:
        if own_clients:
            await role_clients.aclose()
