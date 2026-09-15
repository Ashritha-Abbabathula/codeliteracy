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
