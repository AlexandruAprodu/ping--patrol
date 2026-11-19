import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.users.constants import ROLE_USER


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def database_schema(users_database):
    configured = os.environ.get("TEST_MONITORING_DATABASE_URL")
    if not configured or not (make_url(configured).database or "").endswith("_test"):
        raise RuntimeError("Set TEST_MONITORING_DATABASE_URL to a dedicated database ending in _test.")
    if make_url(configured) == users_database.url:
        raise RuntimeError("Users and Monitoring require separate test databases.")

    from services.monitoring.models import Base

    engine = create_async_engine(configured)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def clients(database_schema, users_client, monkeypatch):
    from common.authentication import auth as auth_module
    from services.monitoring import main as monitoring_main
    from services.users.main import app as users_app

    sessions = async_sessionmaker(database_schema, expire_on_commit=False)

    async def monitor_session():
        async with sessions() as session:
            yield session

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
    previous_overrides = monitoring_main.app.dependency_overrides.copy()
    monitoring_main.app.dependency_overrides[monitoring_main.get_db] = monitor_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=monitoring_main.app),
            base_url="http://localhost:8001",
        ) as monitoring_client:
            yield users_client, monitoring_client, database_schema
    finally:
        monitoring_main.app.dependency_overrides.clear()
        monitoring_main.app.dependency_overrides.update(previous_overrides)


@pytest.fixture
def authenticated_headers(clients):
    async def create(role=ROLE_USER):
        from services.users.db import SessionLocal
        from services.users.models import User

        users, _, _ = clients
        username = f"health_{uuid4().hex[:14]}"
        password = "HealthTestPassword123!"
        response = await users.post("/api/v1/auth/register/", json={
            "email": f"{username}@example.com", "username": username, "password": password,
        })
        assert response.status_code == 201, response.text
        if role != ROLE_USER:
            async with SessionLocal() as session:
                await session.execute(update(User).where(User.id == UUID(response.json()["id"])).values(role=role))
                await session.commit()
        login = await users.post("/api/v1/auth/login", data={"username": username, "password": password})
        assert login.status_code == 200, login.text
        return {"access_token": login.json()["access_token"]}

    return create
