import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User, UserSession


class AuthError(Exception):
    pass


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if not salt:
        salt = os.urandom(16).hex()
    pwd_bytes = password.encode("utf-8")
    salt_bytes = salt.encode("utf-8")
    derived = hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt_bytes, 100000)
    return derived.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    derived, _ = hash_password(password, salt)
    return secrets.compare_digest(derived, expected_hash)


def create_session(db: Session, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    session = UserSession(token=token, user_id=user_id, expires_at=expires_at)
    db.add(session)
    db.commit()
    return token


def revoke_session(db: Session, token: str | None) -> None:
    """Invalidate a session token server-side (logout)."""
    if not token:
        return
    session = db.get(UserSession, token)
    if session:
        db.delete(session)
        db.commit()


def get_user_by_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.get(UserSession, token)
    if not session:
        return None
    if session.expires_at.tzinfo is None:
        expires = session.expires_at.replace(tzinfo=timezone.utc)
    else:
        expires = session.expires_at
    if expires < datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        return None
    return db.get(User, session.user_id)


def register_user(db: Session, username: str, email: str, password: str) -> User:
    username = username.strip()
    email = email.strip().lower()

    if not username or len(username) < 2:
        raise AuthError("Username must be at least 2 characters.")
    if not email or "@" not in email:
        raise AuthError("Please provide a valid email address.")
    if not password or len(password) < 6:
        raise AuthError("Password must be at least 6 characters.")

    if len(username) > 40 or len(password) > 256:
        raise AuthError("Username or password is too long.")

    existing_user = db.scalar(
        select(User).where((func.lower(User.username) == username.lower()) | (User.email == email))
    )
    if existing_user:
        if existing_user.username.lower() == username.lower():
            raise AuthError("That username is already taken.")
        raise AuthError("That email is already registered.")

    pwd_hash, salt = hash_password(password)
    user = User(
        username=username,
        email=email,
        password_hash=pwd_hash,
        salt=salt,
        is_guest=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, login_id: str, password: str) -> User | None:
    login_id = login_id.strip()
    user = db.scalar(
        select(User).where((func.lower(User.username) == login_id.lower()) | (User.email == login_id.lower()))
    )
    if not user:
        return None
    if not verify_password(password, user.salt, user.password_hash):
        return None
    return user


def create_guest_user(db: Session) -> tuple[User, str]:
    guest_suffix = secrets.token_hex(3)
    username = f"Guest_{guest_suffix}"
    email = f"guest_{guest_suffix}@codeliteracy.local"
    random_pw = secrets.token_urlsafe(12)
    pwd_hash, salt = hash_password(random_pw)

    user = User(
        username=username,
        email=email,
        password_hash=pwd_hash,
        salt=salt,
        is_guest=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_session(db, user.id)
    return user, token
