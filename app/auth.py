from __future__ import annotations

import base64
import hashlib
import hmac
import os

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def get_session_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.scalar(select(User).where(User.id == user_id, User.active.is_(True)))
    if not user:
        request.session.clear()
    return user


def can_edit(user: User | None) -> bool:
    return bool(user and user.role in {"ADMIN", "EDITOR"})


def is_admin(user: User | None) -> bool:
    return bool(user and user.role == "ADMIN")
