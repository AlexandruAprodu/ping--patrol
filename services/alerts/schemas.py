from typing import Literal
from pydantic import BaseModel, ConfigDict
from services.incidents.schemas import Incident


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]
    service: Literal["alerts"]


class IncidentSsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident: Incident
