from __future__ import annotations

from enum import StrEnum


class IntentCode(StrEnum):
    visit_book = "visit.book"
    visit_check = "visit.check"
    visit_cancel = "visit.cancel"
    complaint_file = "complaint.file"
    complaint_check = "complaint.check"
    qa_db = "qa.db"
    qa_kb = "qa.kb"
    other = "other"


class AgentName(StrEnum):
    scheduling = "scheduling"
    complaints = "complaints"
    knowledge = "knowledge"
    responder = "responder"


AGENT_FOR_INTENT: dict[IntentCode, AgentName] = {
    IntentCode.visit_book: AgentName.scheduling,
    IntentCode.visit_check: AgentName.scheduling,
    IntentCode.visit_cancel: AgentName.scheduling,
    IntentCode.qa_db: AgentName.scheduling,
    IntentCode.complaint_file: AgentName.complaints,
    IntentCode.complaint_check: AgentName.complaints,
    IntentCode.qa_kb: AgentName.knowledge,
    IntentCode.other: AgentName.responder,
}

FALLBACK_AGENT = AgentName.responder


def agent_for(intent: IntentCode | None) -> AgentName:
    if intent is None:
        return FALLBACK_AGENT
    return AGENT_FOR_INTENT[intent]
