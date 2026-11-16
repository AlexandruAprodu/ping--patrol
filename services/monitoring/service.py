"""Monitoring functions to implement. Contracts: API.md §2, §3, §7."""
from uuid import UUID
from .schemas import CheckResult, Monitor, MonitorCreate


async def create_monitor(body: MonitorCreate) -> Monitor:
    ...


async def list_monitors() -> list[Monitor]:
    ...


async def get_monitor(monitor_id: UUID) -> Monitor:
    ...


async def delete_monitor(monitor_id: UUID) -> None:
    ...


async def probe_http(url: str) -> tuple[bool, int | None, float]:
    ...


async def evaluate_rule_grpc(
    monitor_id: UUID, *, healthy: bool, failure_threshold: int,
    status_code: int | None, latency_ms: float,
) -> tuple[str, int]:
    ...


async def publish_rule_event(transition: str, monitor_id: UUID) -> None:
    ...


async def run_check(monitor_id: UUID) -> CheckResult:
    ...


async def scheduler_loop() -> None:
    ...
