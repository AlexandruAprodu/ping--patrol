"""Alerts domain functions, API.md §5 and §7."""
from collections.abc import AsyncIterator
from uuid import UUID
from services.incidents.schemas import Incident


async def fetch_incident_rest(incident_id: UUID) -> Incident:
    ...


async def broadcast_sse(kind: str, incident: Incident) -> None:
    ...


async def consume_incident_events() -> None:
    ...


async def stream_alerts() -> AsyncIterator[str]:
    ...
a