"""Monitoring HTTP route skeleton. Contracts: API.md §2."""
from uuid import UUID
from fastapi import FastAPI, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from .db import get_db
from .schemas import CheckResult, HealthResponse, Monitor, MonitorCreate

app = FastAPI(title="SignalWatch Monitoring", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ...


@app.post("/monitors", response_model=Monitor,
          status_code=status.HTTP_201_CREATED)
async def create_monitor(body: MonitorCreate,
                         session: AsyncSession = Depends(get_db)) -> Monitor:
    ...



@app.get("/monitors", response_model=list[Monitor])
async def list_monitors() -> list[Monitor]:
    ...


@app.get("/monitors/{monitor_id}", response_model=Monitor)
async def get_monitor(monitor_id: UUID) -> Monitor:
    ...


@app.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(monitor_id: UUID) -> None:
    ...


@app.post("/monitors/{monitor_id}/check", response_model=CheckResult)
async def check_monitor(monitor_id: UUID) -> CheckResult:
    ...
