import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AccountRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class SlotStatus(str, enum.Enum):
    available = "available"
    booked = "booked"


class VisitStatus(str, enum.Enum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"


class ComplaintStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"


class KbFileType(str, enum.Enum):
    pdf = "pdf"
    txt = "txt"
    docx = "docx"


class KbDocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


_pg_account_role = Enum(AccountRole, name="account_role", create_constraint=True)
_pg_slot_status = Enum(SlotStatus, name="slot_status", create_constraint=True)
_pg_visit_status = Enum(VisitStatus, name="visit_status", create_constraint=True)
_pg_complaint_status = Enum(
    ComplaintStatus, name="complaint_status", create_constraint=True
)
_pg_message_role = Enum(MessageRole, name="message_role", create_constraint=True)
_pg_kb_file_type = Enum(KbFileType, name="kb_file_type", create_constraint=True)
_pg_kb_document_status = Enum(
    KbDocumentStatus, name="kb_document_status", create_constraint=True
)


class Account(Base):
    __tablename__ = "account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[AccountRole] = mapped_column(
        _pg_account_role, nullable=False, server_default="user"
    )


class AuthSession(Base):
    __tablename__ = "auth_session"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    active_mode: Mapped[AccountRole] = mapped_column(
        _pg_account_role, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class Location(Base):
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)


class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("account.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    location_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("location.id", ondelete="RESTRICT"),
        nullable=False,
    )


class Clinic(Base):
    __tablename__ = "clinic"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("location.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)


class Specialty(Base):
    __tablename__ = "specialty"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)


class ClinicSpecialty(Base):
    __tablename__ = "clinic_specialty"
    __table_args__ = (
        UniqueConstraint("clinic_id", "specialty_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clinic_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("clinic.id", ondelete="CASCADE"),
        nullable=False,
    )
    specialty_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("specialty.id", ondelete="RESTRICT"),
        nullable=False,
    )


class Doctor(Base):
    __tablename__ = "doctor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clinic_specialty_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("clinic_specialty.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)


class Slot(Base):
    __tablename__ = "slot"
    __table_args__ = (
        UniqueConstraint("doctor_id", "start_at"),
        CheckConstraint(
            "extract(minute from start_at at time zone 'UTC') = 0 "
            "AND extract(second from start_at at time zone 'UTC') = 0",
            name="ck_slot_on_the_hour",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doctor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doctor.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[SlotStatus] = mapped_column(
        _pg_slot_status, nullable=False, server_default="available"
    )


class Visit(Base):
    __tablename__ = "visit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("profile.id", ondelete="RESTRICT"),
        nullable=False,
    )
    slot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("slot.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[VisitStatus] = mapped_column(
        _pg_visit_status, nullable=False, server_default="scheduled"
    )


class Complaint(Base):
    __tablename__ = "complaint"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visit_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("visit.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ComplaintStatus] = mapped_column(
        _pg_complaint_status, nullable=False, server_default="open"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ComplaintReply(Base):
    __tablename__ = "complaint_reply"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    complaint_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("complaint.id", ondelete="CASCADE"),
        nullable=False,
    )
    admin_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("account.id", ondelete="RESTRICT"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatSession(Base):
    __tablename__ = "chat_session"
    __table_args__ = (
        Index("ix_chat_session_profile_last_msg", "profile_id", "last_message_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("profile.id", ondelete="RESTRICT"),
        nullable=False,
    )
    intent: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_message"
    __table_args__ = (
        Index("ix_chat_message_session_id", "session_id", "id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_session.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(_pg_message_role, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # type: ignore[type-arg]
    tool_call_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)


class KbDocument(Base):
    __tablename__ = "kb_document"
    __table_args__ = (
        CheckConstraint("file_size_bytes > 0", name="ck_kb_document_file_size"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[KbFileType] = mapped_column(_pg_kb_file_type, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[KbDocumentStatus] = mapped_column(
        _pg_kb_document_status, nullable=False, server_default="uploaded"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("account.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
