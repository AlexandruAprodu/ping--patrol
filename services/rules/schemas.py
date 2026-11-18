from typing import Literal

from common.schemas import DependencyStatus, ReadinessResponse, StrictModel


class RulesDependencies(StrictModel):
    grpc_server: DependencyStatus
    rule_engine: DependencyStatus


class HealthResponse(ReadinessResponse):
    service: Literal["rules"]
    dependencies: RulesDependencies
