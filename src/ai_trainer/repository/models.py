"""SQLAlchemy-модели предметной области.

Соответствуют `docs/database.md`. Схема меняется только через Alembic-миграции.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ai_trainer.config import get_settings
from ai_trainer.repository.enums import (
    ContentType,
    MessageRole,
    Mode,
    SessionState,
    SourceType,
    Verdict,
    enum_values,
)

_EMBEDDING_DIM = get_settings().embedding_dim


def _enum(enum_cls: type[Any], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=enum_values,
        native_enum=True,
    )


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sessions: Mapped[list[Session]] = relationship(back_populates="user")


class Scenario(Base):
    __tablename__ = "scenarios"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index(
            "uq_sessions_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    scenario_code: Mapped[str | None] = mapped_column(ForeignKey("scenarios.code"))
    mode: Mapped[Mode | None] = mapped_column(_enum(Mode, "mode"))
    state: Mapped[SessionState] = mapped_column(
        _enum(SessionState, "session_state"),
        default=SessionState.idle,
        server_default=SessionState.idle.value,
        nullable=False,
    )
    case_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, nullable=False)
    case_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list[Message]] = relationship(back_populates="session")
    answers: Mapped[list[CaseAnswer]] = relationship(back_populates="session")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole, "message_role"), nullable=False)
    content_type: Mapped[ContentType] = mapped_column(
        _enum(ContentType, "content_type"),
        default=ContentType.text,
        server_default=ContentType.text.value,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="messages")


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scenario_code: Mapped[str] = mapped_column(ForeignKey("scenarios.code"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    expected_points: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    exemplary_answer: Mapped[str] = mapped_column(Text, nullable=False)
    mistake_codes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    document_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CaseAnswer(Base):
    __tablename__ = "case_answers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[Verdict] = mapped_column(_enum(Verdict, "verdict"), nullable=False)
    score: Mapped[int | None] = mapped_column(SmallInteger)
    what_to_improve: Mapped[str | None] = mapped_column(Text)
    example_answer: Mapped[str | None] = mapped_column(Text)
    detected_mistakes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="answers")


class Mistake(Base):
    __tablename__ = "mistake_catalog"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_code: Mapped[str | None] = mapped_column(ForeignKey("scenarios.code"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_examples: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    improved_wording: Mapped[str | None] = mapped_column(Text)
    example_answer: Mapped[str | None] = mapped_column(Text)
    document_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, nullable=False)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scenario_code: Mapped[str | None] = mapped_column(ForeignKey("scenarios.code"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"),
        nullable=False,
    )
    author: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    accessed_at: Mapped[date] = mapped_column(Date, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chunks: Mapped[list[Chunk]] = relationship(back_populates="document")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBEDDING_DIM), nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")
