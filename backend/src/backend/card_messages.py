from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

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


def utc_text(moment: datetime) -> str:
    utc = moment.astimezone(UTC)
    return f"{utc.strftime('%a')} {utc.day} {utc.strftime('%b')}, {utc.strftime('%H:%M')} UTC"


async def slot_label(db: AsyncSession, slot_id: int) -> str:
    row = (
        await db.execute(select(Doctor.name, Slot.start_at).join(Slot, Slot.doctor_id == Doctor.id).where(Slot.id == slot_id))
    ).one()
    return f"{row.name} on {utc_text(row.start_at)}"


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
