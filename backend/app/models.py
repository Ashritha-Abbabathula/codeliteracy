import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Repository(Base):
    """A GitHub repo the user has connected (cloned or linked), plus its cached
    dependency graph so later sprints (explanations, the assistant, quizzes) don't
    need to re-clone or re-parse it on every request."""

    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    source: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(200))
    local_path: Mapped[str] = mapped_column(String(1000))
    graph_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssistantChange(Base):
    """A single FR5-FR7 assistant interaction: what the user asked for, what the
    assistant did about it, and the concept it should quiz the user on next (FR8)."""

    __tablename__ = "assistant_changes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    repo_id: Mapped[str] = mapped_column(String(32))
    request: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    concept: Mapped[str] = mapped_column(String(200))
    steps_json: Mapped[str] = mapped_column(Text)
    files_changed_json: Mapped[str] = mapped_column(Text)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
