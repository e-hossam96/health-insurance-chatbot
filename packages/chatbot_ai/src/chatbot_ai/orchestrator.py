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
from chatbot_ai.agents.knowledge import KnowledgeAgent
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
from chatbot_ai.router import classify, router_messages
from chatbot_ai.settings import AISettings, Role


def default_agents() -> dict[AgentName, Agent]:
    return {
        AgentName.scheduling: scheduling_agent(),
        AgentName.complaints: complaints_agent(),
        AgentName.knowledge: KnowledgeAgent(),
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
    tracer = role_clients.tracer()
    try:
        with tracer.turn(req.session_id) as turn_record:
            turn_record.record(input=req.message)
            started = clock()
            with tracer.stage("classify", "generation", model=role_clients.get(Role.router).model) as classify_record:
                classification = await classify(
                    role_clients.get(Role.router), req.history, req.message, settings.ai_router_history_rows, settings.ai_router_max_output_tokens
                )
                classify_record.record(
                    input=router_messages(req.history, req.message, settings.ai_router_history_rows),
                    output={"intent": classification.intent.value if classification.intent is not None else None},
                    usage=classification.usage,
                )
            classified = clock()
            if req.needs_label and classification.intent is not None:
                yield Intent(code=classification.intent.value)

            agent_name = agent_for(classification.intent)
            agent = registry.get(agent_name)
            if agent is None:
                raise AgentNotAvailable(f"no {agent_name.value} agent is registered")

            context = AgentContext(request=req, ports=ports, settings=settings, clients=role_clients, clock=clock, tracer=tracer)
            result: AgentResult | None = None
            async for event in agent.run(context):
                if isinstance(event, AgentResult):
                    result = event
                else:
                    yield event
            if result is None:
                raise RuntimeError(f"{agent_name.value} agent finished without a result")

            final_rows = [row for row in result.rows if row.role == "assistant" and row.content]
            turn_record.record(output=final_rows[-1].content if final_rows else None)
            yield Done(
                new_rows=[HistoryRow(role="user", content=req.message), *result.rows],
                timings=Timings(
                    classify=classified - started,
                    rewrite=result.stages.get("rewrite", 0.0),
                    embed=result.stages.get("embed", 0.0),
                    search=result.stages.get("search", 0.0),
                    rerank=result.stages.get("rerank", 0.0),
                    ttft=result.ttft,
                    generate=result.generate,
                    total=clock() - started,
                    tool_calls=result.tool_calls,
                ),
                usage=_sum_usage(classification.usage, result.usage),
                agent=agent_name.value,
            )
    finally:
        if own_clients:
            await role_clients.aclose()
