from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from common.schemas import StrictModel


class RegisterRequest(StrictModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(StrictModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(StrictModel):
    id: UUID
    email: EmailStr
    username: str
    created_at: datetime
