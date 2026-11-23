from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from chatbot_ai.agents.knowledge import NOT_FOUND_REPLY
from chatbot_ai.clients import RoleClients
from chatbot_ai.evals.routing import RoutingOutcome, summarize
from chatbot_ai.intents import AgentName, IntentCode
from chatbot_ai.interface import Done, ProfileInfo, Token, TurnEvent, TurnRequest
from chatbot_ai.languages import LanguageCode, script_language
from chatbot_ai.orchestrator import run_turn
from chatbot_ai.prompts import agent_system_prompt, load_prompt
from chatbot_ai.rag.rewrite import rewrite_messages
from chatbot_ai.router import classify
from chatbot_ai.settings import AISettings, Role
from testkit.fake_openai import (
    ChatReply,
    FakeOpenAI,
    error_reply,
    json_reply,
    text_reply,
)
from testkit.fake_ports import fake_ports, sample_catalog

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
