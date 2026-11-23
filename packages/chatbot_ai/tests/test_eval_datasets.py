from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from chatbot_ai.evals.routing import load_routing
from chatbot_ai.evals.schemas import AnswerItem, RetrievalItem, ToolScenario, load_jsonl
from chatbot_ai.intents import IntentCode
from chatbot_ai.languages import LanguageCode
from chatbot_ai.tools.registry import COMPLAINT_TOOLS, SCHEDULING_TOOLS

EVALS = Path(__file__).resolve().parent.parent / "src" / "chatbot_ai" / "evals"
DATASETS = EVALS / "datasets"
FIXTURES = EVALS / "kb_fixtures"
CARD_TYPES = {"doctors", "cancel_confirm", "visits_for_complaint"}


def _fixture_text() -> dict[str, str]:
    pdf = (FIXTURES / "policy_handbook.pdf").read_bytes().decode("latin-1")
    pdf_text = " ".join(m.replace("\\(", "(").replace("\\)", ")") for m in re.findall(r"\(((?:\\.|[^\\)])*)\) Tj", pdf))
    docx_xml = zipfile.ZipFile(io.BytesIO((FIXTURES / "member_guide.docx").read_bytes())).read("word/document.xml").decode("utf-8")
    docx_text = " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", docx_xml))
    return {"policy_handbook.pdf": " ".join(pdf_text.split()), "member_guide.docx": " ".join(docx_text.split())}


def test_retrieval_draft_phrases_exist_in_the_expected_fixture() -> None:
    texts = _fixture_text()
    items = load_jsonl(DATASETS / "retrieval.jsonl", RetrievalItem)
    assert len(items) >= 15
    assert len({i.id for i in items}) == len(items)
    assert {i.expected_document for i in items} == set(texts)
    for item in items:
        for phrase in item.expected_phrases:
            assert phrase in texts[item.expected_document], f"{item.id}: {phrase!r}"


def test_answers_draft_mixes_answerable_and_unanswerable_questions() -> None:
    texts = " ".join(_fixture_text().values())
    items = load_jsonl(DATASETS / "answers.jsonl", AnswerItem)
    answerable = [i for i in items if i.answerable]
    unanswerable = [i for i in items if not i.answerable]
    assert len(answerable) >= 8 and len(unanswerable) >= 4
    assert all(i.must_include for i in answerable) and not any(i.must_include for i in unanswerable)
    for item in answerable:
        for options in item.fact_alternatives():
            assert any(option in texts for option in options), f"{item.id}: {options!r}"


def test_tools_draft_uses_real_tools_and_card_types() -> None:
    known = {t.name for t in SCHEDULING_TOOLS + COMPLAINT_TOOLS}
    scenarios = load_jsonl(DATASETS / "tools.jsonl", ToolScenario)
    assert len(scenarios) >= 6
    for scenario in scenarios:
        for turn in scenario.turns:
            assert {call.name for call in turn.expected_tools} <= known, scenario.id
            assert turn.expected_cards is None or turn.expected_cards in CARD_TYPES
    cross = next(s for s in scenarios if s.id == "cross-agent")
    assert [t.expected_intent.value for t in cross.turns] == ["visit.book", "qa.kb", "visit.book"]


def test_a_required_fact_passes_when_any_of_its_wordings_is_in_the_answer() -> None:
    item = AnswerItem(id="x", question="q", answerable=True, must_include=["50 EGP", ["not cover", "excluded"]])
    assert item.facts_in("Cosmetic surgery is Excluded; the co-pay is 50 egp.")
    assert item.facts_in("The plan does not cover it. Co-pay: 50 EGP.")
    assert not item.facts_in("Cosmetic surgery is excluded.")
    assert not item.facts_in("The co-pay is 50 EGP and cosmetic surgery is covered.")
    assert item.facts_in("The co-pay is **50** EGP and cosmetic surgery is **excluded**.")


def test_F17_every_dataset_has_arabic_and_other_language_items() -> None:
    answers = load_jsonl(DATASETS / "answers.jsonl", AnswerItem)
    scenarios = load_jsonl(DATASETS / "tools.jsonl", ToolScenario)
    routing = load_routing(DATASETS / "routing.jsonl")
    assert {i.expected_language for i in routing} == set(LanguageCode)
    assert {i.expected for i in routing if i.expected_language is LanguageCode.arabic} == set(IntentCode)
    assert {i.expected_language for i in answers} == set(LanguageCode)
    assert any(not i.answerable for i in answers if i.expected_language is LanguageCode.arabic)
    turns = [turn for scenario in scenarios for turn in scenario.turns]
    assert {t.expected_cards for t in turns if t.expected_language is LanguageCode.arabic} >= CARD_TYPES
    retrieval = load_jsonl(DATASETS / "retrieval.jsonl", RetrievalItem)
    assert {i.expected_language for i in retrieval} == set(LanguageCode)
    assert {i.expected_document for i in retrieval if i.expected_language is LanguageCode.arabic} == {"policy_handbook.pdf", "member_guide.docx"}
    switch = next(s for s in scenarios if s.id == "language-switch")
    assert [t.expected_language for t in switch.turns] == [LanguageCode.english, LanguageCode.arabic, LanguageCode.arabic]
