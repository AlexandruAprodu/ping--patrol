from typing import Literal

from common.schemas import DependencyStatus, ReadinessResponse, StrictModel
from services.incidents.schemas import Incident


class AlertsDependencies(StrictModel):
    rabbitmq: DependencyStatus
    incidents_rest: DependencyStatus
    consumer: DependencyStatus
    sse_dispatcher: DependencyStatus


class HealthResponse(ReadinessResponse):
    service: Literal["alerts"]
    dependencies: AlertsDependencies


class IncidentSsePayload(StrictModel):
    incident: Incident
