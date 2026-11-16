from __future__ import annotations

import json
from typing import Any

JsonObject = dict[str, Any]  # Any: OpenAI wire-format messages

AUTO_TEXT = "Streaming check: one two three four five six."
NO_SLOTS_TEXT = "Sorry, no doctor of that specialty has an available slot right now."
UNKNOWN_SPECIALTY_TEXT = "I could not find that specialty in the catalog."
ROUTES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("cancel",), "visit.cancel"),
    (("complain", "complaint"), "complaint.file"),
    (("my visits", "my appointments"), "visit.check"),
    (("cover", "co-pay", "copay", "policy", "claim"), "qa.kb"),
    (("book", "doctor", "specialist", "need a", "appointment", "ologist", "pediatric", "orthoped"), "visit.book"),
)


def _last_user_message(messages: list[JsonObject]) -> str:
    return next((str(m.get("content") or "") for m in reversed(messages) if m.get("role") == "user"), "")


def classify(messages: list[JsonObject]) -> str:
    text = _last_user_message(messages).lower()
    for keywords, intent in ROUTES:
        if any(keyword in text for keyword in keywords):
            return intent
    return "other"


def _tool_name_for(messages: list[JsonObject], call_id: str) -> str:
    for message in messages:
        for call in message.get("tool_calls") or []:
            if call.get("id") == call_id:
                return str(call["function"]["name"])
    return ""


def _stem(name: str) -> str:
    return name.lower()[:6]


def _options_text(cards: list[JsonObject]) -> str:
    options = "; ".join(f"{c['doctor_name']} at {c['clinic']} on {str(c['start_at']).replace('T', ' ').replace(':00Z', '')} UTC" for c in cards)
    return f"Here are the earliest options: {options}. Click a card to book."


def scheduling_step(messages: list[JsonObject], tool_names: set[str]) -> tuple[str | None, tuple[str, JsonObject] | None]:
    last = messages[-1]
    if last.get("role") == "user":
        if "list_specialties" in tool_names:
            return None, ("list_specialties", {})
        return AUTO_TEXT, None
    if last.get("role") != "tool":
        return AUTO_TEXT, None
    name = _tool_name_for(messages, str(last.get("tool_call_id", "")))
    result = json.loads(str(last.get("content") or "{}"))
    if name == "list_specialties":
        wanted = _last_user_message(messages).lower()
        match = next((s for s in result.get("specialties", []) if _stem(s["name"]) in wanted), None)
        if match is None:
            return UNKNOWN_SPECIALTY_TEXT, None
        return None, ("recommend_doctors", {"specialty_id": match["id"]})
    if name == "recommend_doctors":
        cards = result.get("shown_as_cards", [])
        return (_options_text(cards) if cards else NO_SLOTS_TEXT), None
    return "Done.", None
