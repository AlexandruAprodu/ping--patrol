from typing import Literal
from pydantic import Field, field_validator

from common.schemas import StrictModel


class Mode(StrictModel):
    status_code: int = Field(default=200, ge=200, le=599, strict=True)
    delay_ms: int = Field(default=0, ge=0, le=10_000, strict=True)

    @field_validator("status_code")
    @classmethod
    def no_bodyless_http_codes(cls, value: int) -> int:
        if value in (204, 205, 304):
            raise ValueError("Status code cannot have a JSON response body")
        return value


class TargetHealth(StrictModel):
    service: Literal["fake-target"]
    healthy: bool
