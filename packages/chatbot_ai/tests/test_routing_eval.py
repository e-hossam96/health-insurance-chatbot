from __future__ import annotations

import json
from pathlib import Path

import pytest

from chatbot_ai.evals.__main__ import (
    DATASETS_DIR,
    EvalUsageError,
    main,
    parse_overrides,
)
from chatbot_ai.evals.routing import RoutingOutcome, load_routing, summarize
from chatbot_ai.intents import IntentCode
from testkit.fake_openai import FakeOpenAI, json_reply

STARTER_MESSAGES = {
    "I'd like to book a clinic visit.": "visit.book",
    "Show me my visits.": "visit.check",
    "I want to cancel a visit.": "visit.cancel",
    "I want to file a complaint about a visit.": "complaint.file",
    "Show me my complaints.": "complaint.check",
    "What does my health insurance cover?": "qa.kb",
}


def test_draft_routing_dataset_covers_every_intent_and_the_starter_cards() -> None:
    items = load_routing(DATASETS_DIR / "routing.jsonl")
    assert {item.expected for item in items} == set(IntentCode)
    by_message = {item.message: item.expected.value for item in items}
    for message, intent in STARTER_MESSAGES.items():
        assert by_message[message] == intent
    assert any(item.history for item in items), "follow-ups need prior rows"
    assert len({item.id for item in items}) == len(items)


def test_summary_computes_accuracy_recall_and_confusion() -> None:
    outcomes = [
        RoutingOutcome(id="a", expected="visit.book", predicted="visit.book", latency_s=0.1),
        RoutingOutcome(id="b", expected="visit.book", predicted="qa.db", latency_s=0.3),
        RoutingOutcome(id="c", expected="qa.kb", predicted="qa.kb", latency_s=0.2),
        RoutingOutcome(id="d", expected="other", predicted="none", latency_s=0.2),
    ]
    report = summarize(outcomes)
    assert report.accuracy == 0.5
    assert report.recall == {"other": 0.0, "qa.kb": 1.0, "visit.book": 0.5}
    assert report.confusion["visit.book"] == {"visit.book": 1, "qa.db": 1}
    assert [m.id for m in report.mistakes] == ["b", "d"]
    assert report.mean_latency_s == pytest.approx(0.2)


def test_routing_eval_runs_on_the_draft_dataset_and_writes_reports(fake_openai: FakeOpenAI, tmp_path: Path) -> None:
    smoke_items = load_routing(DATASETS_DIR / "routing.jsonl")[:5]
    predictions = [item.expected.value for item in smoke_items]
    predictions[1] = "other"
    fake_openai.queue(*(json_reply({"intent": p}) for p in predictions), model="router-model")

    code = main(
        [
            "routing",
            "--smoke",
            "--set", f"ai_router_base_url={fake_openai.base_url}",
            "--set", "ai_router_model=router-model",
            "--set", "openai_api_key=test-key",
            "--set", "ai_max_retries=0",
            "--set", "ai_embedding_dimensions=64",
            "--set", "qdrant_url=http://127.0.0.1:6333",
        ],
        out_dir=tmp_path,
    )

    assert code == 0
    assert len(fake_openai.chat_requests) == 5
    report_json = next(tmp_path.glob("routing-*.json"))
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    assert payload["result"]["items"] == 5
    assert payload["result"]["accuracy"] == pytest.approx(0.8)
    assert payload["config"]["roles"]["router"] == {"base_url": fake_openai.base_url, "model": "router-model"}
    assert "test-key" not in report_json.read_text(encoding="utf-8")
    assert next(tmp_path.glob("routing-*.md")).read_text(encoding="utf-8").startswith("# routing eval")


def test_cli_rejects_unknown_settings_and_unsupported_flags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(EvalUsageError):
        parse_overrides(["no-equals-sign"])
    assert main(["routing", "--set", "ai_not_a_setting=1"], out_dir=tmp_path) == 2
    assert "unknown setting" in capsys.readouterr().err
    assert main(["routing", "--langfuse", "--set", "ai_embedding_dimensions=8", "--set", "qdrant_url=http://q"], out_dir=tmp_path) == 2
    assert "--langfuse" in capsys.readouterr().err
