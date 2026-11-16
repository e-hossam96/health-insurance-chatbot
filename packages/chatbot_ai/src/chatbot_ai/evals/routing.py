from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from chatbot_ai.clients import RoleClient
from chatbot_ai.intents import IntentCode
from chatbot_ai.interface import HistoryRow
from chatbot_ai.router import classify

NO_INTENT = "none"


class HistoryTurn(BaseModel):
    role: str
    content: str


class RoutingItem(BaseModel):
    id: str
    message: str
    history: list[HistoryTurn] = Field(default_factory=list)
    expected: IntentCode


class RoutingOutcome(BaseModel):
    id: str
    expected: str
    predicted: str
    latency_s: float


class RoutingReport(BaseModel):
    items: int
    accuracy: float
    recall: dict[str, float]
    confusion: dict[str, dict[str, int]]
    mistakes: list[RoutingOutcome]
    mean_latency_s: float


def load_routing(path: Path) -> list[RoutingItem]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [RoutingItem.model_validate_json(line) for line in lines if line.strip()]


def summarize(outcomes: list[RoutingOutcome]) -> RoutingReport:
    confusion: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        row = confusion.setdefault(outcome.expected, {})
        row[outcome.predicted] = row.get(outcome.predicted, 0) + 1
    expected_counts = Counter(o.expected for o in outcomes)
    correct = [o for o in outcomes if o.expected == o.predicted]
    correct_counts = Counter(o.expected for o in correct)
    return RoutingReport(
        items=len(outcomes),
        accuracy=len(correct) / len(outcomes) if outcomes else 0.0,
        recall={code: correct_counts[code] / count for code, count in sorted(expected_counts.items())},
        confusion=confusion,
        mistakes=[o for o in outcomes if o.expected != o.predicted],
        mean_latency_s=sum(o.latency_s for o in outcomes) / len(outcomes) if outcomes else 0.0,
    )


async def run_routing(
    items: list[RoutingItem], router: RoleClient, window_size: int, clock: Callable[[], float] = time.monotonic, max_tokens: int = 512
) -> RoutingReport:
    outcomes: list[RoutingOutcome] = []
    for item in items:
        history = [HistoryRow(role=turn.role, content=turn.content) for turn in item.history]
        started = clock()
        classification = await classify(router, history, item.message, window_size, max_tokens)
        outcomes.append(
            RoutingOutcome(
                id=item.id,
                expected=item.expected.value,
                predicted=classification.intent.value if classification.intent else NO_INTENT,
                latency_s=clock() - started,
            )
        )
    return summarize(outcomes)
