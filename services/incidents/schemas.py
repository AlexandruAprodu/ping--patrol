from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, StringConstraints


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


IncidentStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]


class HealthResponse(StrictModel):
    status: Literal["ok"]
    service: Literal["incidents"]


class Incident(StrictModel):
    id: UUID
    monitor_id: UUID
    title: Literal["HTTP monitor unavailable"]
    severity: Literal["critical"]
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime


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
