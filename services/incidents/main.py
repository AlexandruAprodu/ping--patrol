"""Incidents HTTP and WebSocket endpoint skeleton, API.md §4."""
from uuid import UUID
from fastapi import FastAPI, WebSocket
from .schemas import HealthResponse, Incident, IncidentStatus

app = FastAPI(title="SignalWatch Incidents", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ...


@app.get("/incidents", response_model=list[Incident])
async def list_incidents(
    monitor_id: UUID | None = None, status: IncidentStatus | None = None
) -> list[Incident]:
    ...


@app.get("/incidents/{incident_id}", response_model=Incident)
async def get_incident(incident_id: UUID) -> Incident:
    ...


@app.post("/incidents/{incident_id}/ack", response_model=Incident)
async def acknowledge_incident(incident_id: UUID) -> Incident:
    ...


@app.websocket("/ws/incidents/{incident_id}")
async def incident_websocket(websocket: WebSocket, incident_id: str) -> None:
    ...
