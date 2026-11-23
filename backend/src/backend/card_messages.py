from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import ChatMessage, Doctor, MessageRole, Slot


class MessageOut(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    tool_calls: object | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None

    @classmethod
    def from_row(cls, message: ChatMessage) -> MessageOut:
        return cls(
            id=message.id,
            session_id=message.session_id,
            role=message.role.value,
            content=message.content,
            tool_calls=message.tool_calls,
            tool_call_id=message.tool_call_id,
            tool_name=message.tool_name,
        )


@dataclass(frozen=True)
class CardAction:
    user_text: str
    tool_name: str
    tool_call_id: str
    arguments: dict[str, int]
    result: dict[str, int | str]
    reply: str


CardLanguage = Literal["en", "ar"]


@dataclass(frozen=True)
class CardTexts:
    book_user: str
    book_reply: str
    cancel_user: str
    cancel_reply: str
    complaint_user: str
    complaint_reply: str
    slot: str


CARD_TEXTS: dict[CardLanguage, CardTexts] = {
    "en": CardTexts(
        book_user="Book {slot}.",
        book_reply="Your visit has been booked successfully.",
        cancel_user="Cancel my visit with {slot}.",
        cancel_reply="Your visit has been cancelled.",
        complaint_user="File a complaint about my visit with {slot}.",
        complaint_reply="Your complaint has been filed.",
        slot="{doctor} on {when}",
    ),
    "ar": CardTexts(
        book_user="احجز موعدًا مع {slot}.",
        book_reply="تم حجز موعدك بنجاح.",
        cancel_user="ألغِ موعدي مع {slot}.",
        cancel_reply="تم إلغاء موعدك.",
        complaint_user="أريد تقديم شكوى بشأن موعدي مع {slot}.",
        complaint_reply="تم تقديم شكواك.",
        slot="{doctor} يوم {when}",
    ),
}

ARABIC_WEEKDAYS = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
ARABIC_MONTHS = ("يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر")


def utc_text(moment: datetime, language: CardLanguage = "en") -> str:
    utc = moment.astimezone(UTC)
    if language == "ar":
        return f"{ARABIC_WEEKDAYS[utc.weekday()]} {utc.day} {ARABIC_MONTHS[utc.month - 1]}، {utc.strftime('%H:%M')} UTC"
    return f"{utc.strftime('%a')} {utc.day} {utc.strftime('%b')}, {utc.strftime('%H:%M')} UTC"


async def slot_label(db: AsyncSession, slot_id: int, language: CardLanguage = "en") -> str:
    row = (
        await db.execute(select(Doctor.name, Slot.start_at).join(Slot, Slot.doctor_id == Doctor.id).where(Slot.id == slot_id))
    ).one()
    return CARD_TEXTS[language].slot.format(doctor=row.name, when=utc_text(row.start_at, language))


async def write_card_action_messages(db: AsyncSession, chat_session_id: int, action: CardAction) -> list[MessageOut]:
    tool_calls = [
        {
            "id": action.tool_call_id,
            "type": "function",
            "function": {"name": action.tool_name, "arguments": json.dumps(action.arguments)},
        }
    ]
    rows = [
        ChatMessage(session_id=chat_session_id, role=MessageRole.user, content=action.user_text),
        ChatMessage(session_id=chat_session_id, role=MessageRole.assistant, content="", tool_calls=tool_calls),
        ChatMessage(
            session_id=chat_session_id,
            role=MessageRole.tool,
            content=json.dumps(action.result),
            tool_call_id=action.tool_call_id,
            tool_name=action.tool_name,
        ),
        ChatMessage(session_id=chat_session_id, role=MessageRole.assistant, content=action.reply),
    ]
    for row in rows:
        # one flush per row keeps the ids in conversation order
        db.add(row)
        await db.flush()
    return [MessageOut.from_row(row) for row in rows]
