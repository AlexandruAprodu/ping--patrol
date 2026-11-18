import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from .constants import ACCESS_TOKEN, ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM
from .db import get_db
from .models import User


def load_jwt_secret() -> str:
    configured = os.getenv("USERS_JWT_SECRET") or os.getenv("JWT_SECRET")
    if configured:
        if len(configured.encode()) < 32:
            raise RuntimeError("USERS_JWT_SECRET must contain at least 32 bytes.")
        return configured
    path = Path(__file__).with_name(".jwt_secret")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text().strip()
    with os.fdopen(descriptor, "w") as file:
        secret = secrets.token_urlsafe(48)
        file.write(secret)
    return secret


JWT_SECRET = load_jwt_secret()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "type": ACCESS_TOKEN, "iat": now,
         "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)},
        JWT_SECRET, algorithm=JWT_ALGORITHM,
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=401, detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
        if payload["type"] != ACCESS_TOKEN:
            raise unauthorized
        user_id = UUID(payload["sub"])
    except (PyJWTError, ValueError, TypeError) as exc:
        raise unauthorized from exc
    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized
    return user
