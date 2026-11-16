"""Incidents domain functions to implement, API.md §4 and §7."""
from uuid import UUID
from fastapi import WebSocket
from .schemas import Incident, IncidentStatus, CommentInput


async def list_incidents(
    monitor_id: UUID | None = None, status: IncidentStatus | None = None
) -> list[Incident]:
    ...


async def get_incident(incident_id: UUID) -> Incident:
    ...


async def acknowledge_incident(incident_id: UUID) -> Incident:
    ...


async def consume_rule_events() -> None:
    ...


async def process_rule_event(message: dict) -> None:
    ...


async def publish_incident_event(kind: str, incident_id: UUID) -> None:
    ...


async def broadcast_comment(incident_id: UUID, comment: CommentInput) -> None:
    ...


async def handle_websocket(websocket: WebSocket, incident_id: str) -> None:
    ...
