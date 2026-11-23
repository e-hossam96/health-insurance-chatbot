from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from chatbot_ai.agents.knowledge import NOT_FOUND_REPLY, retrieval_mode
from chatbot_ai.clients import RoleClients
from chatbot_ai.evals.routing import RoutingOutcome, summarize
from chatbot_ai.intents import AgentName, IntentCode
from chatbot_ai.interface import Cards, Done, ProfileInfo, Token, TurnEvent, TurnRequest
from chatbot_ai.languages import LanguageCode, script_language
from chatbot_ai.orchestrator import run_turn
from chatbot_ai.prompts import agent_system_prompt, load_prompt
from chatbot_ai.rag.rewrite import rewrite_messages, rewrite_question
from chatbot_ai.router import classify
from chatbot_ai.settings import AISettings, Role
from testkit.fake_openai import (
    ChatReply,
    FakeOpenAI,
    ToolCallSpec,
    error_reply,
    json_reply,
    text_reply,
    tool_reply,
)
from testkit.fake_ports import fake_ports, make_fake_ports, sample_catalog

PROFILE = ProfileInfo(display_name="Mona", location_name="Cairo", location_id=1)
PORTS = fake_ports(sample_catalog(), profile_id=10, profile_location_id=1, now=datetime(2026, 12, 1, tzinfo=UTC))
MSA = "Modern Standard Arabic"
AMERICAN = "American English"
ARABIC_GREETING = "مرحبا، أريد حجز موعد"
ARABIC_NOT_FOUND = "لم أجد ذلك في المستندات."


def _request(message: str) -> TurnRequest:
    return TurnRequest(history=[], message=message, profile=PROFILE, needs_label=False, session_id=7)


async def _collect(events: AsyncIterator[TurnEvent]) -> list[TurnEvent]:
    return [event async for event in events]


def test_F17_script_language_spots_arabic_letters() -> None:
    assert script_language(ARABIC_GREETING) is LanguageCode.arabic
    assert script_language("Is maternity covered? نعم") is LanguageCode.arabic
    assert script_language("Is maternity covered?") is LanguageCode.english
    assert script_language("Bonjour") is LanguageCode.english
    assert script_language("") is LanguageCode.english


@pytest.mark.anyio()
async def test_I1_F17_classifier_asks_for_intent_and_language_in_one_structured_output(
    fake_openai: FakeOpenAI, role_clients: RoleClients
) -> None:
    fake_openai.queue(json_reply({"intent": "qa.kb", "language": "ar"}), model="router-model")
    result = await classify(role_clients.get(Role.router), [], "هل الولادة مغطاة؟", 6)
    assert result.intent is IntentCode.qa_kb
    assert result.language is LanguageCode.arabic
    assert len(fake_openai.chat_requests) == 1
    schema = fake_openai.chat_requests[0]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["language"]["enum"] == ["ar", "en", "other"]
    assert schema["required"] == ["intent", "language"]
    assert "Language codes" in fake_openai.chat_requests[0]["messages"][0]["content"]


@pytest.mark.anyio()
@pytest.mark.parametrize(
    ("reply", "message", "intent", "language"),
    [
        (error_reply(500, "router down"), ARABIC_GREETING, None, LanguageCode.arabic),
        (error_reply(500, "router down"), "Hola, quiero una cita", None, LanguageCode.english),
        (text_reply("not json"), ARABIC_GREETING, None, LanguageCode.arabic),
        (text_reply('{"intent": "visit.book", "language": "fr"}'), ARABIC_GREETING, IntentCode.visit_book, LanguageCode.arabic),
        (text_reply('{"intent": "visit.nope", "language": "other"}'), "Hola", None, LanguageCode.other),
    ],
    ids=["error-arabic", "error-latin", "unparseable", "bad-language-keeps-intent", "bad-intent-keeps-language"],
)
async def test_I1_F17_an_unusable_label_falls_back_on_its_own(
    fake_openai: FakeOpenAI,
    role_clients: RoleClients,
    reply: ChatReply,
    message: str,
    intent: IntentCode | None,
    language: LanguageCode,
) -> None:
    fake_openai.queue(reply, model="router-model")
    result = await classify(role_clients.get(Role.router), [], message, 6)
    assert result.intent is intent
    assert result.language is language


@pytest.mark.anyio()
@pytest.mark.parametrize(
    ("language", "expected", "absent"),
    [("ar", MSA, AMERICAN), ("en", AMERICAN, MSA), ("other", AMERICAN, MSA)],
    ids=["arabic-gets-msa", "english-gets-american", "other-gets-american"],
)
async def test_F17_the_turn_reply_language_follows_the_classified_language(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients, language: str, expected: str, absent: str
) -> None:
    fake_openai.queue(json_reply({"intent": "other", "language": language}), model="router-model")
    fake_openai.queue(text_reply("ok"), model="chat-model")
    await _collect(run_turn(_request("hello"), PORTS, ai_settings, role_clients))
    system = fake_openai.chat_requests[1]["messages"][0]["content"]
    assert system == agent_system_prompt(AgentName.responder, PROFILE, LanguageCode(language))
    assert expected in system
    assert absent not in system


@pytest.mark.anyio()
async def test_F17_the_tool_agents_get_the_reply_language_too(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients
) -> None:
    fake_openai.queue(json_reply({"intent": "visit.check", "language": "ar"}), model="router-model")
    fake_openai.queue(text_reply("مواعيدك"), model="chat-model")
    await _collect(run_turn(_request("أرني مواعيدي"), PORTS, ai_settings, role_clients))
    assert MSA in fake_openai.chat_requests[1]["messages"][0]["content"]


def test_F17_every_agent_prompt_puts_the_reply_language_after_the_shared_rules() -> None:
    for agent in AgentName:
        for language in LanguageCode:
            prompt = agent_system_prompt(agent, PROFILE, language)
            assert "English only" not in prompt
            marker = MSA if language is LanguageCode.arabic else AMERICAN
            assert prompt.index("in the reply language given below") < prompt.index(marker) < prompt.index(load_prompt(agent.value))


@pytest.mark.anyio()
@pytest.mark.parametrize(("language", "refusal"), [("ar", ARABIC_NOT_FOUND), ("en", NOT_FOUND_REPLY), ("other", NOT_FOUND_REPLY)])
async def test_F17_I8_the_fixed_not_found_reply_is_in_the_reply_language(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients, language: str, refusal: str
) -> None:
    fake_openai.queue(json_reply({"intent": "qa.kb", "language": language}), model="router-model")
    fake_openai.queue(json_reply({"standalone": "Is cosmetic surgery covered?", "alternates": []}), model="rewrite-model")
    events = await _collect(run_turn(_request("cosmetic surgery?"), PORTS, ai_settings, role_clients))
    assert [e.text for e in events if isinstance(e, Token)] == [refusal]
    done = events[-1]
    assert isinstance(done, Done)
    assert done.new_rows[-1].content == refusal


def test_F17_the_rewrite_asks_for_english_search_queries() -> None:
    system = rewrite_messages([], "هل الولادة مغطاة؟", 3)[0]
    assert system["role"] == "system"
    assert 'write "standalone" and every alternate in English' in str(system.get("content"))


def test_F17_routing_eval_scores_the_language_label_separately() -> None:
    outcomes = [
        RoutingOutcome(id="a", expected="other", predicted="other", latency_s=0.1, expected_language="ar", predicted_language="ar"),
        RoutingOutcome(id="b", expected="other", predicted="other", latency_s=0.1, expected_language="ar", predicted_language="en"),
        RoutingOutcome(id="c", expected="qa.kb", predicted="other", latency_s=0.1),
    ]
    report = summarize(outcomes)
    assert report.accuracy == pytest.approx(2 / 3)
    assert report.language_accuracy == pytest.approx(2 / 3)
    assert [m.id for m in report.language_mistakes] == ["b"]
    assert [m.id for m in report.mistakes] == ["c"]


@pytest.mark.anyio()
@pytest.mark.parametrize(("language", "card_language"), [("ar", "ar"), ("en", "en"), ("other", "en")])
async def test_F17_cards_carry_the_turn_language_and_keep_the_catalog_names(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients, language: str, card_language: str
) -> None:
    ports = make_fake_ports(sample_catalog(), profile_id=10, profile_location_id=1, now=datetime(2026, 12, 1, tzinfo=UTC))
    fake_openai.queue(json_reply({"intent": "visit.book", "language": language}), model="router-model")
    fake_openai.queue(
        tool_reply(ToolCallSpec("list_specialties", {}, id="c1")),
        tool_reply(ToolCallSpec("recommend_doctors", {"specialty_id": 1}, id="c2")),
        text_reply("ok"),
        model="chat-model",
    )
    events = await _collect(run_turn(_request("dermatologist"), ports.as_ports(), ai_settings, role_clients))
    cards = next(e for e in events if isinstance(e, Cards))
    assert cards.language is LanguageCode(card_language)
    catalog_doctors = {doctor.name for doctor in sample_catalog().doctors}
    assert cards.items and all(item["doctor_name"] in catalog_doctors for item in cards.items)


def test_F17_the_english_block_forbids_mirroring_another_language() -> None:
    english = load_prompt("language_english")
    assert "never reply in the member's language when it is not English" in english


def test_F17_the_arabic_block_translates_document_text_but_keeps_catalog_names() -> None:
    arabic = load_prompt("language_arabic")
    assert "Translate everything you take from the tools or documents into Arabic" in arabic
    assert "keep doctor, clinic, location and specialty names exactly as the tools give them" in arabic
    assert "The cards are shown in English" not in arabic


def test_I1_F8_a_described_health_problem_routes_to_booking() -> None:
    assert "describes a health problem or asks for medical advice should see a doctor: give visit.book" in load_prompt("router")


def test_I6_F17_the_rewrite_always_asks_for_the_alternates_it_has_room_for() -> None:
    system = str(rewrite_messages([], "هل الولادة مغطاة؟", 3)[0].get("content"))
    assert 'always fill it with exactly 2 different phrasings' in system and "never leave it empty" in system
    assert "If asked for alternates" not in system


@pytest.mark.anyio()
@pytest.mark.parametrize(("intent", "language"), [("other", "other"), ("visit.check", "other"), ("other", "en"), ("visit.check", "ar")])
async def test_F17_only_an_other_language_turn_ends_with_the_english_reminder_and_it_is_not_stored(
    fake_openai: FakeOpenAI, ai_settings: AISettings, role_clients: RoleClients, intent: str, language: str
) -> None:
    fake_openai.queue(json_reply({"intent": intent, "language": language}), model="router-model")
    fake_openai.queue(text_reply("ok"), model="chat-model")
    events = await _collect(run_turn(_request("Bonjour, mes rendez-vous ?"), PORTS, ai_settings, role_clients))
    messages = fake_openai.chat_requests[1]["messages"]
    reminder = {"role": "system", "content": load_prompt("language_other_reminder")}
    if language == "other":
        assert messages[-1] == reminder
        assert messages[-2] == {"role": "user", "content": "Bonjour, mes rendez-vous ?"}
    else:
        assert reminder not in messages
    done = events[-1]
    assert isinstance(done, Done)
    assert all(row.role != "system" for row in done.new_rows)


@pytest.mark.anyio()
async def test_I6_F17_a_failed_rewrite_is_flagged_and_a_non_english_turn_then_searches_dense_only(
    fake_openai: FakeOpenAI, role_clients: RoleClients, ai_settings: AISettings
) -> None:
    fake_openai.queue(error_reply(500, "rewrite down"), model="rewrite-model")
    failed = await rewrite_question(role_clients.get(Role.rewrite), [], "هل الولادة مغطاة؟", 3)
    assert failed.fell_back and failed.queries == ["هل الولادة مغطاة؟"]
    fake_openai.queue(json_reply({"standalone": "Is maternity covered?", "alternates": ["a", "b"]}), model="rewrite-model")
    rewritten = await rewrite_question(role_clients.get(Role.rewrite), [], "هل الولادة مغطاة؟", 3)
    assert not rewritten.fell_back

    hybrid = ai_settings.model_copy(update={"ai_retrieval_mode": "hybrid"})
    assert retrieval_mode(failed, LanguageCode.arabic, hybrid) == "dense"
    assert retrieval_mode(failed, LanguageCode.other, hybrid) == "dense"
    assert retrieval_mode(failed, LanguageCode.english, hybrid) == "hybrid"
    assert retrieval_mode(rewritten, LanguageCode.arabic, hybrid) == "hybrid"
    sparse = ai_settings.model_copy(update={"ai_retrieval_mode": "sparse"})
    assert retrieval_mode(failed, LanguageCode.arabic, sparse) == "sparse", "an explicit ablation setting is kept"
