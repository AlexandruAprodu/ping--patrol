from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Mode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status_code: int = Field(default=200, ge=200, le=599, strict=True)
    delay_ms: int = Field(default=0, ge=0, le=10_000, strict=True)

    @field_validator("status_code")
    @classmethod
    def no_bodyless_http_codes(cls, value: int) -> int:
        if value in (204, 205, 304):
            raise ValueError("Status code cannot have a JSON response body")
        return value


class TargetHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service: Literal["fake-target"]
    healthy: bool
