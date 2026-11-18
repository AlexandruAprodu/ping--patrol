import os
from types import SimpleNamespace

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def database_schema():
    users_url = os.environ.get("USERS_DATABASE_URL")
    monitoring_url = os.environ.get("TEST_MONITORING_DATABASE_URL")

    if not users_url or not monitoring_url:
        raise RuntimeError("Set USERS_DATABASE_URL and TEST_MONITORING_DATABASE_URL to dedicated test databases.")
    if not users_url.split("?")[0].endswith("_test") or not monitoring_url.split("?")[0].endswith("_test"):
        raise RuntimeError("Integration tests refuse to modify databases not ending in _test.")

    from services.users import db as users_db
    from services.users.models import Base as UsersBase
    from services.monitoring.models import Base as MonitoringBase

    if str(users_db.engine.url) != users_url:
        raise RuntimeError("The Users engine must point to USERS_DATABASE_URL before importing the service.")

    monitoring_engine = create_async_engine(monitoring_url)
    try:
        async with users_db.engine.begin() as connection:
            await connection.run_sync(UsersBase.metadata.drop_all)
            await connection.run_sync(UsersBase.metadata.create_all)
        async with monitoring_engine.begin() as connection:
            await connection.run_sync(MonitoringBase.metadata.drop_all)
            await connection.run_sync(MonitoringBase.metadata.create_all)

        yield monitoring_engine
    finally:
        async with monitoring_engine.begin() as connection:
            await connection.run_sync(MonitoringBase.metadata.drop_all)
        async with users_db.engine.begin() as connection:
            await connection.run_sync(UsersBase.metadata.drop_all)
        await monitoring_engine.dispose()
        await users_db.engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def clients(database_schema, monkeypatch):
    from common.authentication import auth as auth_module
    from services.monitoring import main as monitoring_main
    from services.users.main import app as users_app

    session_factory = async_sessionmaker(database_schema, expire_on_commit=False)

    async def test_monitor_session():
        async with session_factory() as session:
            yield session

    # The real Monitoring middleware still calls the real Users /me endpoint.
    # Only the HTTP network transport is replaced with an in-process ASGI transport.
    monkeypatch.setattr(
        auth_module,
        "httpx",
        SimpleNamespace(
            AsyncClient=lambda: httpx.AsyncClient(
                transport=httpx.ASGITransport(app=users_app),
                base_url="http://localhost:8005",
            )
        ),
    )

    monitoring_main.app.dependency_overrides[monitoring_main.get_db] = test_monitor_session
    try:
        async with (
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=users_app),
                base_url="http://localhost:8005",
            ) as users_client,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=monitoring_main.app),
                base_url="http://localhost:8001",
            ) as monitoring_client,
        ):
            yield users_client, monitoring_client, database_schema
    finally:
        monitoring_main.app.dependency_overrides.clear()
