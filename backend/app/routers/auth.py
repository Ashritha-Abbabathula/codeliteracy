from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import extract_token, get_current_user, get_current_user_optional  # noqa: F401 - re-exported
from app.models import NotebookEntry, Repository, User
from app.services.auth_service import (
    AuthError,
    authenticate_user,
    create_guest_user,
    create_session,
    register_user,
    revoke_session,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    login_id: str  # username or email
    password: str


class UserPublic(BaseModel):
    id: str
    username: str
    email: str
    is_guest: bool
    created_at: str


class UserStats(BaseModel):
    repos_count: int
    notebook_count: int
    quizzes_passed: int


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class MeResponse(BaseModel):
    user: UserPublic
    stats: UserStats


def _to_user_public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id,
        username=user.username,
        email=user.email,
        is_guest=user.is_guest,
        created_at=user.created_at.isoformat(),
    )


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    try:
        user = register_user(db, payload.username, payload.email, payload.password)
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = create_session(db, user.id)
    return AuthResponse(token=token, user=_to_user_public(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = authenticate_user(db, payload.login_id, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password.",
        )

    token = create_session(db, user.id)
    return AuthResponse(token=token, user=_to_user_public(user))


@router.post("/guest", response_model=AuthResponse)
def guest_login(db: Session = Depends(get_db)) -> AuthResponse:
    user, token = create_guest_user(db)
    return AuthResponse(token=token, user=_to_user_public(user))


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    repos_count = db.scalar(
        select(func.count()).select_from(Repository).where(Repository.user_id == user.id)
    ) or 0
    notebook_count = db.scalar(
        select(func.count()).select_from(NotebookEntry).where(NotebookEntry.user_id == user.id)
    ) or 0
    quizzes_passed = db.scalar(
        select(func.count()).select_from(NotebookEntry).where(
            NotebookEntry.user_id == user.id, NotebookEntry.quiz_id.is_not(None)
        )
    ) or 0

    return MeResponse(
        user=_to_user_public(user),
        stats=UserStats(
            repos_count=repos_count,
            notebook_count=notebook_count,
            quizzes_passed=quizzes_passed,
        ),
    )


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    x_auth_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    """Revoke the session token so it can't be replayed after sign-out."""
    revoke_session(db, extract_token(authorization, x_auth_token))
    return {"success": True}
