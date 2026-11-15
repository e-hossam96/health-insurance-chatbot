from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from chatbot_ai.intents import IntentCode


class RetrievalItem(BaseModel):
    id: str
    question: str
    expected_phrases: list[str] = Field(min_length=1)
    expected_document: str


class AnswerItem(BaseModel):
    id: str
    question: str
    answerable: bool
    must_include: list[str] = Field(default_factory=list)


class ExpectedToolCall(BaseModel):
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)


class ScenarioTurn(BaseModel):
    message: str
    expected_intent: IntentCode
    expected_tools: list[ExpectedToolCall] = Field(default_factory=list)
    expected_cards: str | None = None


class ToolScenario(BaseModel):
    id: str
    description: str
    turns: list[ScenarioTurn] = Field(min_length=1)


def load_jsonl[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    return [model.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
