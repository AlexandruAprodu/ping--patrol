import os

import httpx
import pytest_asyncio
from sqlalchemy.engine import make_url


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def users_database():
    configured = os.environ.get("USERS_DATABASE_URL")
    if not configured or not (make_url(configured).database or "").endswith("_test"):
        raise RuntimeError("Set USERS_DATABASE_URL to a dedicated database ending in _test.")

    from services.users import db as users_db
    from services.users.models import Base

    if users_db.engine.url != make_url(configured):
        raise RuntimeError("Configure USERS_DATABASE_URL before importing the Users service.")

    try:
        async with users_db.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        yield users_db.engine
    finally:
        async with users_db.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await users_db.engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def users_client(users_database):
    from services.users.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://localhost:8005",
    ) as client:
        yield client
