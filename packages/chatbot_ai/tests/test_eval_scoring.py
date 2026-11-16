from __future__ import annotations

import pytest

from chatbot_ai.evals.schemas import RetrievalItem
from chatbot_ai.evals.suites import _scores, is_refusal, stale_slot_mentions
from chatbot_ai.rag.search import Candidate


def _candidate(content: str, document_id: int = 1) -> Candidate:
    return Candidate(
        point_id=content,
        content=content,
        headings=(),
        content_hash=content,
        document_id=document_id,
    )


ITEM = RetrievalItem(
    id="copay",
    question="What is the co-pay?",
    expected_phrases=["50 EGP", "per visit"],
    expected_document="policy_handbook.pdf",
)


def test_retrieval_metrics_on_a_known_ranking() -> None:
    ranked = [_candidate(f"filler {i}") for i in range(6)] + [
        _candidate("co-pay of 50 EGP"),
        _candidate("charged per visit"),
    ]
    hits, recall, reciprocal_rank = _scores(ranked, ITEM)
    assert hits == {5: False, 10: True}
    assert recall == {5: 0.0, 10: 1.0}
    assert reciprocal_rank == pytest.approx(1 / 7)


def test_retrieval_metrics_ignore_the_right_text_from_the_wrong_document() -> None:
    ranked = [
        _candidate("co-pay of 50 EGP", document_id=2),
        _candidate("50 EGP per visit"),
    ]
    hits, recall, reciprocal_rank = _scores(ranked, ITEM)
    assert hits == {5: True, 10: True}
    assert recall[5] == 1.0
    assert reciprocal_rank == 0.5


def test_no_relevant_passage_scores_zero() -> None:
    hits, recall, reciprocal_rank = _scores([_candidate("nothing useful")], ITEM)
    assert (
        hits == {5: False, 10: False}
        and recall == {5: 0.0, 10: 0.0}
        and reciprocal_rank == 0.0
    )


def test_a_slot_time_from_an_earlier_turn_repeated_without_a_new_search_is_stale() -> (
    None
):
    earlier = '[{"doctor": "Dr. Sara", "start_at": "2026-12-15T10:00:00+00:00"}]'
    assert stale_slot_mentions(earlier, "", "Dr. Sara is still free at 10:00 UTC.") == 1
    assert (
        stale_slot_mentions(
            earlier,
            '[{"start_at": "2026-12-15T10:00:00+00:00"}]',
            "Dr. Sara is free at 10:00 UTC.",
        )
        == 0
    )
    assert (
        stale_slot_mentions(
            earlier,
            '[{"start_at": "2026-12-16T11:00:00+00:00"}]',
            "Dr. Lina is free at 11:00 UTC.",
        )
        == 0
    )


def test_refusals_trust_the_judge_and_otherwise_need_an_opening_refusal() -> None:
    hedged = "Outside the network is not covered except in an emergency. I could not find more detail."
    assert is_refusal(hedged, judged_refusal=None) is False
    assert (
        is_refusal("I couldn't find that in the documents.", judged_refusal=None)
        is True
    )
    assert is_refusal(hedged, judged_refusal=True) is True
    assert (
        is_refusal("I couldn't find that in the documents.", judged_refusal=False)
        is False
    )
