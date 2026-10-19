"""Shared request helpers: who is calling, and which data they're allowed to see.

Isolation rule: a signed-in user sees only their own repositories/quizzes/notebook; an
anonymous visitor sees only anonymous (user_id NULL) data. Someone else's repository is
reported as "not found", not "forbidden", so its existence isn't revealed."""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Repository, User
from app.services.auth_service import get_user_by_token


def extract_token(authorization: str | None, x_auth_token: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split("Bearer ", 1)[1].strip() or None
    if x_auth_token:
        return x_auth_token.strip() or None
    return None


def get_current_user_optional(
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    token = extract_token(authorization, x_auth_token)
    return get_user_by_token(db, token) if token else None


def get_current_user(user: User | None = Depends(get_current_user_optional)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required. Please sign in.")
    return user


def owner_id(user: User | None) -> str | None:
    return user.id if user else None


def owned_by(column, user: User | None):
    """SQL filter: rows belonging to this user (or to anonymous visitors if not signed in)."""
    return column == user.id if user else column.is_(None)


def get_owned_repo(db: Session, repo_id: str, user: User | None) -> Repository:
    repo = db.get(Repository, repo_id)
    if repo is None or repo.user_id != owner_id(user):
        raise HTTPException(status_code=404, detail="Repository not found.")
    return repo
