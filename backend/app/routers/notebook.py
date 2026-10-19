from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user_optional, owned_by, owner_id
from app.models import NotebookEntry, User
from app.schemas import NotebookEntryCreate, NotebookEntryPublic, NotebookEntryUpdate

router = APIRouter(prefix="/api/notebook", tags=["notebook"])


def _owned_entry(db: Session, entry_id: str, user: User | None) -> NotebookEntry:
    entry = db.get(NotebookEntry, entry_id)
    if entry is None or entry.user_id != owner_id(user):
        raise HTTPException(status_code=404, detail="Notebook entry not found.")
    return entry


@router.get("", response_model=list[NotebookEntryPublic])
def list_notebook(
    q: str | None = Query(default=None),
    repo: str | None = Query(default=None),
    category: str | None = Query(default=None),
    favorites: bool = Query(default=False),
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> list[NotebookEntry]:
    """The learner's notebook, newest first, searchable by concept, repo, file, summary or note."""
    stmt = select(NotebookEntry).where(owned_by(NotebookEntry.user_id, user)).order_by(NotebookEntry.created_at.desc())

    if repo:
        stmt = stmt.where(NotebookEntry.repo_name.ilike(f"%{repo}%"))
    if category:
        stmt = stmt.where(NotebookEntry.category == category)
    if favorites:
        stmt = stmt.where(NotebookEntry.is_favorite.is_(True))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            NotebookEntry.concept.ilike(pattern)
            | NotebookEntry.repo_name.ilike(pattern)
            | NotebookEntry.summary.ilike(pattern)
            | NotebookEntry.question.ilike(pattern)
            | NotebookEntry.file_path.ilike(pattern)
            | NotebookEntry.user_notes.ilike(pattern)
        )
    return list(db.scalars(stmt))


@router.post("", response_model=NotebookEntryPublic)
def create_notebook_entry(
    payload: NotebookEntryCreate,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> NotebookEntry:
    """A learner's own note (not tied to a quiz)."""
    if not payload.concept.strip() or not payload.summary.strip():
        raise HTTPException(status_code=400, detail="A note needs a title and some text.")
    entry = NotebookEntry(
        user_id=owner_id(user),
        concept=payload.concept.strip()[:200],
        question=payload.question,
        summary=payload.summary.strip(),
        repo_name=payload.repo_name,
        file_path=payload.file_path,
        code_snippet=payload.code_snippet,
        user_notes=payload.user_notes,
        category=payload.category,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=NotebookEntryPublic)
def update_notebook_entry(
    entry_id: str,
    payload: NotebookEntryUpdate,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> NotebookEntry:
    entry = _owned_entry(db, entry_id, user)
    entry.user_notes = payload.user_notes.strip() or None
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{entry_id}/favorite", response_model=NotebookEntryPublic)
def toggle_favorite(
    entry_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> NotebookEntry:
    entry = _owned_entry(db, entry_id, user)
    entry.is_favorite = not entry.is_favorite
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def delete_notebook_entry(
    entry_id: str,
    user: User | None = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    entry = _owned_entry(db, entry_id, user)
    db.delete(entry)
    db.commit()
    return {"success": True}
