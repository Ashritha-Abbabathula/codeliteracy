from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import NotebookEntry
from app.schemas import NotebookEntryPublic

router = APIRouter(prefix="/api/notebook", tags=["notebook"])


@router.get("", response_model=list[NotebookEntryPublic])
def list_notebook(q: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[NotebookEntry]:
    """FR12: the notebook, searchable by concept/repo/summary, newest first."""
    stmt = select(NotebookEntry).order_by(NotebookEntry.created_at.desc())
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            NotebookEntry.concept.ilike(pattern)
            | NotebookEntry.repo_name.ilike(pattern)
            | NotebookEntry.summary.ilike(pattern)
        )
    return list(db.scalars(stmt))
