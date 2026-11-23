from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from chatbot_ai.evals.__main__ import main
from testkit.fake_openai import FakeOpenAI
from testkit.qdrant import qdrant_url

ROLES = ("chat", "router", "rewrite", "embedding", "judge")


@pytest.fixture()
def auto(fake_openai: FakeOpenAI) -> Iterator[FakeOpenAI]:
    fake_openai.auto = True
    yield fake_openai
    fake_openai.auto = False


def _args(fake: FakeOpenAI, suite: str) -> list[str]:
    overrides = [
        "openai_api_key=test-key",
        "ai_max_retries=0",
        "ai_embedding_dimensions=64",
        f"qdrant_url={qdrant_url()}",
        *(f"ai_{role}_base_url={fake.base_url}" for role in ROLES),
        *(f"ai_{role}_model={role}-model" for role in ROLES),
    ]
    return [suite, "--smoke", *(item for pair in overrides for item in ("--set", pair))]


def _report(out_dir: Path, suite: str) -> dict[str, object]:
    path = next(out_dir.glob(f"{suite}-*.json"))
    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    assert next(out_dir.glob(f"{suite}-*.md")).read_text(encoding="utf-8").startswith(f"# {suite} eval")
    return payload


def test_ingest_suite_checks_the_fixtures_without_model_calls(auto: FakeOpenAI, tmp_path: Path) -> None:
    assert main(_args(auto, "ingest"), out_dir=tmp_path) == 0
    result = _report(tmp_path, "ingest")["result"]
    assert isinstance(result, dict)
    assert result["passed"] is True and result["empty_chunks"] == 0 and result["split_tables_missing_header"] == 0
    assert set(result["documents"]) == {"policy_handbook.pdf", "member_guide.docx"}
    assert auto.chat_requests == [] and auto.embedding_requests == []


def test_retrieval_suite_reports_metrics_after_every_stage(auto: FakeOpenAI, tmp_path: Path) -> None:
    assert main(_args(auto, "retrieval"), out_dir=tmp_path) == 0
    result = _report(tmp_path, "retrieval")["result"]
    assert isinstance(result, dict)
    assert result["items"] == 5
    assert set(result["stages"]) == {"first_query", "fused", "deduped", "reranked"}
    for scores in result["stages"].values():
        assert set(scores["hit"]) == {"@5", "@10"} and 0.0 <= scores["mrr"] <= 1.0
    assert set(result["mean_latency_s"]) == {"rewrite", "embed", "search", "rerank"}
    assert result["stages"]["reranked"]["hit"]["@10"] > 0.5, "hash embeddings find most fixture phrases"
    assert len(result["rewrites"]) == 5 and all(len(r["queries"]) == len(r["english"]) for r in result["rewrites"])
    assert 0.0 <= result["english_query_rate"] <= 1.0 and result["mean_queries"] >= 1.0
    assert set(result["hit_at_5_by_language"]) == {"en"}


def test_answers_suite_judges_answers_and_refusals(auto: FakeOpenAI, tmp_path: Path) -> None:
    assert main(_args(auto, "answers"), out_dir=tmp_path) == 0
    result = _report(tmp_path, "answers")["result"]
    assert isinstance(result, dict)
    assert result["items"] == 5 and result["judge_errors"] == 0
    assert any(r["model"] == "judge-model" for r in auto.chat_requests)
    assert all(set(o) >= {"id", "answer", "refused", "correct_refusal"} for o in result["outcomes"])
    judge_request = next(r for r in auto.chat_requests if r["model"] == "judge-model")
    assert "answer_language" in judge_request["response_format"]["json_schema"]["schema"]["required"]
    assert all(o["reply_language"] == "en" for o in result["outcomes"]), "the judge's language label is the reply language"
    assert result["reply_language_accuracy"] == 1.0


def test_tools_suite_scores_tool_calls_and_cards(auto: FakeOpenAI, tmp_path: Path) -> None:
    assert main(_args(auto, "tools"), out_dir=tmp_path) == 0
    result = _report(tmp_path, "tools")["result"]
    assert isinstance(result, dict)
    outcomes = {o["scenario"]: o for o in result["outcomes"]}
    assert outcomes["recommend-derm"]["tools"] == ["list_specialties", "recommend_doctors"]
    assert outcomes["recommend-derm"]["cards"] == "doctors" and outcomes["recommend-derm"]["passed"] is True
    assert 0.0 < result["turn_pass_rate"] <= 1.0
