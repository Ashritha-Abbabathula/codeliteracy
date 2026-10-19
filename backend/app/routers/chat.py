import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_optional, get_owned_repo, owned_by, owner_id
from app.models import ChatMessage, User
from app.services.chat_service import ChatError, chat_with_tutor

router = APIRouter(prefix="/api/repo", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    context: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    reply: str
    suggested_followups: list[str]
    sources: list[str] = []  # files the tutor was shown when answering (openable in the inspector)


class MessageItem(BaseModel):
    id: str
    role: str
    content: str
    context_type: str | None
    created_at: str


@router.post("/{repo_id}/chat", response_model=ChatResponse)
def send_chat_message(
    repo_id: str,
    payload: ChatRequest,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> ChatResponse:
    repository = get_owned_repo(db, repo_id, user)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if len(message) > 4000:
        raise HTTPException(status_code=400, detail="Message is too long (4000 characters max).")

    recent = list(db.scalars(
        select(ChatMessage)
        .where(ChatMessage.repo_id == repo_id, owned_by(ChatMessage.user_id, user))
        .order_by(ChatMessage.created_at.desc())
        .limit(8)
    ))
    history = [(m.role, m.content) for m in reversed(recent)]

    try:
        result = chat_with_tutor(
            repository.local_path, message, payload.context, history,
            graph=json.loads(repository.graph_json) if repository.graph_json else None,
            project_summary=(json.loads(repository.onboarding_json).get("main_idea") if repository.onboarding_json else None),
        )
    except ChatError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Only persist a turn once it has a real reply (no orphaned questions after a failure).
    context_type = (payload.context or {}).get("context_type")
    db.add(ChatMessage(repo_id=repo_id, user_id=owner_id(user), role="user", content=message, context_type=context_type))
    db.add(ChatMessage(repo_id=repo_id, user_id=owner_id(user), role="assistant", content=result["reply"], context_type=context_type))
    db.commit()

    return ChatResponse(
        reply=result["reply"], suggested_followups=result["suggested_followups"], sources=result["sources"]
    )


@router.delete("/{repo_id}/chat/history")
def clear_chat_history(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Start the conversation over (the tutor then stops referring back to old turns)."""
    get_owned_repo(db, repo_id, user)
    for row in db.scalars(select(ChatMessage).where(ChatMessage.repo_id == repo_id, owned_by(ChatMessage.user_id, user))):
        db.delete(row)
    db.commit()
    return {"success": True}


@router.get("/{repo_id}/chat/history", response_model=list[MessageItem])
def get_chat_history(
    repo_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> list[MessageItem]:
    get_owned_repo(db, repo_id, user)
    rows = list(db.scalars(
        select(ChatMessage)
        .where(ChatMessage.repo_id == repo_id, owned_by(ChatMessage.user_id, user))
        .order_by(ChatMessage.created_at.desc())
        .limit(50)
    ))
    return [
        MessageItem(id=m.id, role=m.role, content=m.content, context_type=m.context_type, created_at=m.created_at.isoformat())
        for m in reversed(rows)
    ]
