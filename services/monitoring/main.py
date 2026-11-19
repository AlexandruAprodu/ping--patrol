"""Monitoring HTTP route skeleton. Contracts: API.md §2."""
from uuid import UUID

from common.authentication.auth import verify_auth_user_middleware
from fastapi import FastAPI, status, Depends, Request, Response, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from .constants import MAXIMUM_MONITORS
from .db import get_db
from .models import MonitorModel
from .schemas import CheckResult, HealthResponse, Monitor, MonitorCreate, MonitorList


app = FastAPI(title="SignalWatch Monitoring", version="1.0.0")

@app.middleware("http")
async def verify_user_auth(request: Request, call_next):
    current_user = await verify_auth_user_middleware(request=request)

    if "Invalid or expired token." in current_user.values():
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    request.state.user_id = current_user.get("id")
    request.state.role = current_user.get("role")
    response = await call_next(request)
    return response


@app.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:

    if not request.state.role == "ADMIN":
        raise HTTPException(status_code=404,
                            detail="Page not found!"
                            )

    from common.health import check_infrastructure


    report = await check_infrastructure()

    if report.get("status") == "unhealthy":
        services_down = [
            name
            for name, service in report.get("services", {}).items()
            if service["status"] == "down"
        ]

        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Services unhealthy: {services_down}")

    return report


@app.post("/monitors", response_model=Monitor,
          status_code=status.HTTP_201_CREATED)
async def create_monitor(request: Request, body: MonitorCreate,
                         session: AsyncSession = Depends(get_db)) -> Monitor:

    owner_count_monitors = await session.scalar(select(func.count()).select_from(
        MonitorModel).where(
        MonitorModel.owner_id == UUID(str(request.state.user_id))
    ))
    if owner_count_monitors and owner_count_monitors >= MAXIMUM_MONITORS:
        raise HTTPException(status_code=403,
                            detail="The maximum numbers of monitors for this "
                                   "account has been reached!"
                            )

    if await session.scalar(select(MonitorModel.url).where(
            MonitorModel.url == str(body.url),
                        MonitorModel.owner_id == UUID(str(request.state.user_id)))
    ):
        raise HTTPException(status_code=409,
                            detail="Monitor URL already exists"
                            )



    monitor = MonitorModel(
        owner_id=UUID(str(request.state.user_id)),
        **body.model_dump(mode="json"),
    )

    session.add(monitor)
    await session.flush()
    await session.commit()

    return Monitor(
        id=monitor.id,
        name=monitor.name,
        url=monitor.url,
        interval_seconds=monitor.interval_seconds,
        failure_threshold=monitor.failure_threshold,
        created_at=monitor.created_at,
    )


@app.get("/monitors", response_model=list[Monitor])
async def list_monitors(request: Request,
                        session: AsyncSession = Depends(get_db)) -> MonitorList:
    monitors_current_user = await session.scalars(select(
        MonitorModel).where(
        MonitorModel.owner_id == UUID(str(request.state.user_id))
    ).order_by(MonitorModel.created_at.desc()))

    return monitors_current_user


@app.get("/monitors/{monitor_id}", response_model=Monitor)
async def get_monitor(monitor_id: UUID, request: Request,
                        session: AsyncSession = Depends(get_db)) -> Monitor:

    monitor = await session.scalar(select(MonitorModel).where(
            MonitorModel.id == UUID(str(monitor_id)),
                        MonitorModel.owner_id == UUID(str(request.state.user_id))))

    if not monitor:
        raise HTTPException(status_code=404,
                            detail="Monitor not found!"
                            )

    return monitor


@app.delete("/monitors/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(monitor_id: UUID, request: Request,
                        session: AsyncSession = Depends(get_db)) -> None:
    monitor = await session.scalar(select(MonitorModel).where(
        MonitorModel.id == UUID(str(monitor_id)),
        MonitorModel.owner_id == UUID(str(request.state.user_id))))

    if not monitor:
        raise HTTPException(status_code=404,
                            detail="Monitor not found!"
                            )

    await session.delete(monitor)
    await session.flush([monitor])
    await session.commit()
    return


@app.post("/monitors/{monitor_id}/check", response_model=CheckResult)
async def check_monitor(monitor_id: UUID) -> CheckResult:
    ...
