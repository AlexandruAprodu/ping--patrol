from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import StringConstraints

from common.schemas import DependencyStatus, ReadinessResponse, StrictModel


IncidentStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]


class IncidentsDependencies(StrictModel):
    postgresql: DependencyStatus
    rabbitmq: DependencyStatus
    consumer: DependencyStatus


class HealthResponse(ReadinessResponse):
    service: Literal["incidents"]
    dependencies: IncidentsDependencies


class Incident(StrictModel):
    id: UUID
    monitor_id: UUID
    title: Literal["HTTP monitor unavailable"]
    severity: Literal["critical"]
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime


class OwnedIncident(Incident):
    owner_id: UUID


class CommentInput(StrictModel):
    type: Literal["comment"]
    author: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class CommentAdded(StrictModel):
    type: Literal["comment_added"]
    incident_id: UUID
    author: str
    text: str
    created_at: datetime
