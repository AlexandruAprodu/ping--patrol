from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, HttpUrl, StringConstraints, field_validator

from common.schemas import DependencyStatus, ReadinessResponse, StrictModel


class MonitoringDependencies(StrictModel):
    postgresql: DependencyStatus
    rules_grpc: DependencyStatus
    rabbitmq: DependencyStatus
    scheduler: DependencyStatus


class HealthResponse(ReadinessResponse):
    service: Literal["monitoring"]
    dependencies: MonitoringDependencies


class MonitorCreate(StrictModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    url: HttpUrl
    interval_seconds: int = Field(default=60, ge=5, le=3600, strict=True)
    failure_threshold: int = Field(default=3, ge=1, le=10, strict=True)

    @field_validator("url")
    @classmethod
    def no_url_auth(cls, value: HttpUrl) -> HttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("URL credentials are not supported")
        return value


class Monitor(MonitorCreate):
    id: UUID
    created_at: datetime


class CheckResult(StrictModel):
    monitor_id: UUID
    checked_at: datetime
    healthy: bool
    status_code: int | None = Field(ge=200, le=599)
    latency_ms: float = Field(ge=0)
    transition: Literal["NONE", "TRIGGERED", "RECOVERED"]
    consecutive_failures: int = Field(ge=0)
