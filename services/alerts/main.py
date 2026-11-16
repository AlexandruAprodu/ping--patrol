"""Alerts HTTP and SSE endpoints, API.md §5."""
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from .schemas import HealthResponse

app = FastAPI(title="SignalWatch Alerts", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ...


@app.get("/alerts/stream", response_class=StreamingResponse)
async def alerts_stream() -> StreamingResponse:
    ...
