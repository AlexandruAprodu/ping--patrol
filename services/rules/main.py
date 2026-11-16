"""Rules HTTP liveness route. gRPC handler lives in grpc_server.py."""
from fastapi import FastAPI
from .schemas import HealthResponse

app = FastAPI(title="SignalWatch Rules Engine", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ...
