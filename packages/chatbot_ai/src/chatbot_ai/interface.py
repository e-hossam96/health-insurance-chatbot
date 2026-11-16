from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from chatbot_ai.tools.ports import ComplaintsPort, KnowledgePort, Ports, SchedulingPort


@dataclass(frozen=True)
class ProfileInfo:
    display_name: str
    location_name: str
    location_id: int


@dataclass(frozen=True)
class HistoryRow:
    role: str
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass(frozen=True)
class TurnRequest:
    history: list[HistoryRow]
    message: str
    profile: ProfileInfo
    needs_label: bool
    session_id: int


@dataclass(frozen=True)
class Intent:
    code: str


@dataclass(frozen=True)
class Token:
    text: str
    elapsed: float


@dataclass(frozen=True)
class Cards:
    type: str
    items: list[dict[str, Any]]


@dataclass(frozen=True)
class Timings:
    classify: float = 0.0
    rewrite: float = 0.0
    embed: float = 0.0
    search: float = 0.0
    rerank: float = 0.0
    ttft: float = 0.0
    generate: float = 0.0
    total: float = 0.0
    tool_calls: list[tuple[str, float]] = field(default_factory=list)


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class Done:
    new_rows: list[HistoryRow]
    timings: Timings = field(default_factory=Timings)
    usage: Usage = field(default_factory=Usage)
    agent: str = ""


TurnEvent = Intent | Token | Cards | Done

TurnRunner = Callable[["TurnRequest"], AsyncIterator[TurnEvent]]


__all__ = [
    "Cards",
    "ComplaintsPort",
    "Done",
    "HistoryRow",
    "Intent",
    "KnowledgePort",
    "Ports",
    "ProfileInfo",
    "SchedulingPort",
    "Timings",
    "Token",
    "TurnEvent",
    "TurnRequest",
    "TurnRunner",
    "Usage",
]
