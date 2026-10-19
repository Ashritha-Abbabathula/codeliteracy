import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """User account for persisting repositories, sessions, and learning notebooks."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    salt: Mapped[str] = mapped_column(String(64))
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserSession(Base):
    """Authentication session token mapped to a user."""

    __tablename__ = "user_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Repository(Base):
    """A GitHub repo the user has connected (cloned or linked), plus its cached
    dependency graph, onboarding analysis, and clean architecture flowchart."""

    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(500))
    name: Mapped[str] = mapped_column(String(200))
    local_path: Mapped[str] = mapped_column(String(1000))
    graph_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    onboarding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    flowchart_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # path -> {"overview", "line_sections", "quiz_ids"}: cached per-file analysis, so
    # re-opening a file is instant and its quizzes keep stable ids (answers are verified
    # server-side against these rows).
    file_details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssistantChange(Base):
    """A single assistant interaction: what the user asked for, what the
    assistant did about it, and the concept it should quiz the user on next."""

    __tablename__ = "assistant_changes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    repo_id: Mapped[str] = mapped_column(String(32), index=True)
    request: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    concept: Mapped[str] = mapped_column(String(200))
    steps_json: Mapped[str] = mapped_column(Text)
    files_changed_json: Mapped[str] = mapped_column(Text)
    diff_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # What the assistant looked at and did, in order (shown as its "work log").
    activity_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A short beginner-level explanation of `concept`, and how to check the change works.
    concept_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    verify: Mapped[str | None] = mapped_column(Text, nullable=True)
    # path -> {"before": original text or null (new file), "after_sha": hash of what was
    # written}. Lets a change be undone safely (only if the file is still as the AI left it).
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reverted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Quiz(Base):
    """Multiple-choice question targeting concepts from an assistant change or a file."""

    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    change_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    repo_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    concept: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text)
    options_json: Mapped[str] = mapped_column(Text)
    correct_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Teaching material generated with the question: a nudge that doesn't give the answer away,
    # why each option is right/wrong (same order as options_json), and what to read up on.
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    option_notes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Learner progress on this question. Two tries: the first wrong one earns a hint, not the answer.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_choice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_choice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    solved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    # Set when the learner asked for a fresh question in this one's place (FR10).
    replaced_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class NotebookEntry(Base):
    """Concepts the user answered correctly or saved notes on, kept for later review."""

    __tablename__ = "notebook_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    quiz_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    concept: Mapped[str] = mapped_column(String(200))
    question: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    repo_name: Mapped[str] = mapped_column(String(200))
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="concept")
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ChatMessage(Base):
    """Persistent chat messages for repo onboarding, file inquiries, and in-chat quiz discussion."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    repo_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    context_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "quiz_discussion", "file", "onboarding"
    context_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
