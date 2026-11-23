from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Protocol

from chatbot_ai.clients import RoleClients
from chatbot_ai.intents import AgentName
from chatbot_ai.interface import Cards, HistoryRow, Ports, Token, TurnRequest, Usage
from chatbot_ai.languages import LanguageCode
from chatbot_ai.settings import AISettings
from chatbot_ai.tracing import TurnTracer

Clock = Callable[[], float]


@dataclass(frozen=True)
class AgentContext:
    request: TurnRequest
    ports: Ports
    settings: AISettings
    clients: RoleClients
    clock: Clock
    tracer: TurnTracer
    language: LanguageCode


@dataclass(frozen=True)
class AgentResult:
    rows: list[HistoryRow]
    usage: Usage = field(default_factory=Usage)
    ttft: float = 0.0
    generate: float = 0.0
    tool_calls: list[tuple[str, float]] = field(default_factory=list)
    stages: dict[str, float] = field(default_factory=dict)


AgentEvent = Token | Cards | AgentResult


class Agent(Protocol):
    name: AgentName

    def run(self, context: AgentContext) -> AsyncIterator[AgentEvent]: ...


class AgentNotAvailable(LookupError):
    pass
