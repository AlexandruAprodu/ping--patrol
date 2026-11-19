from uuid import UUID, uuid4

import pytest
from sqlalchemy import select


pytestmark = pytest.mark.asyncio(loop_scope="session")


def user_payload():
    key = uuid4().hex[:14]
    return {
        "email": f"{key}@example.com",
        "username": f"user_{key}",
        "password": "SafePassword123!",
    }


def monitor_payload():
    return {
        "name": "Payments API",
        "url": f"https://{uuid4().hex}.example.com/health",
        "interval_seconds": 60,
        "failure_threshold": 3,
    }


async def authenticated_user(users_client):
    data = user_payload()
    registered = await users_client.post("/api/v1/auth/register/", json=data)
    assert registered.status_code == 201, registered.text

    logged_in = await users_client.post(
        "/api/v1/auth/login",
        data={"username": data["username"], "password": data["password"]},
    )
    assert logged_in.status_code == 200, logged_in.text
    return UUID(registered.json()["id"]), logged_in.json()["access_token"]


async def test_create_monitor_persists_owner_and_returns_201(clients):
    users, monitoring, monitoring_engine = clients
    user_id, token = await authenticated_user(users)
    payload = monitor_payload()

    response = await monitoring.post(
        "/monitors", json=payload, headers={"access_token": token}
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert UUID(created["id"])
    assert created["name"] == payload["name"]
    assert created["url"] == payload["url"]
    assert created["interval_seconds"] == payload["interval_seconds"]
    assert created["failure_threshold"] == payload["failure_threshold"]
    assert created["created_at"]
    assert "owner_id" not in created

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from services.monitoring.models import MonitorModel

    async with async_sessionmaker(monitoring_engine)() as session:
        persisted = await session.get(MonitorModel, UUID(created["id"]))
        assert persisted is not None
        assert persisted.owner_id == user_id
        assert persisted.name == payload["name"]
        assert persisted.url == payload["url"]


async def test_defaults_and_trimming_are_persisted(clients):
    users, monitoring, monitoring_engine = clients
    user_id, token = await authenticated_user(users)
    payload = {"name": "  Default Monitor  ", "url": f"https://{uuid4().hex}.example.com/health"}

    response = await monitoring.post(
        "/monitors", json=payload, headers={"access_token": token}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Default Monitor"
    assert body["interval_seconds"] == 60
    assert body["failure_threshold"] == 3

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from services.monitoring.models import MonitorModel
    async with async_sessionmaker(monitoring_engine)() as session:
        persisted = await session.get(MonitorModel, UUID(body["id"]))
        assert persisted.owner_id == user_id
        assert persisted.name == "Default Monitor"


async def test_duplicate_url_is_rejected_for_same_owner(clients):
    users, monitoring, monitoring_engine = clients
    user_id, token = await authenticated_user(users)
    payload = monitor_payload()
    headers = {"access_token": token}
    first = await monitoring.post("/monitors", json=payload, headers=headers)
    assert first.status_code == 201, first.text

    duplicate = await monitoring.post(
        "/monitors", json={**payload, "name": "Another name"}, headers=headers
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "Monitor URL already exists"}

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from services.monitoring.models import MonitorModel
    async with async_sessionmaker(monitoring_engine)() as session:
        rows = (await session.scalars(
            select(MonitorModel).where(
                MonitorModel.owner_id == user_id,
                MonitorModel.url == payload["url"],
            )
        )).all()
        assert len(rows) == 1


async def test_same_url_is_allowed_for_different_users(clients):
    users, monitoring, monitoring_engine = clients
    owner_a, token_a = await authenticated_user(users)
    owner_b, token_b = await authenticated_user(users)
    payload = monitor_payload()

    first = await monitoring.post("/monitors", json=payload, headers={"access_token": token_a})
    second = await monitoring.post("/monitors", json=payload, headers={"access_token": token_b})
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] != second.json()["id"]

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from services.monitoring.models import MonitorModel
    async with async_sessionmaker(monitoring_engine)() as session:
        stored_a = await session.get(MonitorModel, UUID(first.json()["id"]))
        stored_b = await session.get(MonitorModel, UUID(second.json()["id"]))
        assert stored_a.owner_id == owner_a
        assert stored_b.owner_id == owner_b


async def test_missing_or_invalid_token_returns_401_without_insert(clients):
    _, monitoring, _ = clients
    payload = monitor_payload()

    missing = await monitoring.post("/monitors", json=payload)
    assert missing.status_code == 401

    invalid = await monitoring.post(
        "/monitors", json=payload, headers={"access_token": "not-a-jwt"}
    )
    assert invalid.status_code == 401


async def test_invalid_monitor_payload_returns_422(clients):
    users, monitoring, _ = clients
    _, token = await authenticated_user(users)
    headers = {"access_token": token}
    valid = monitor_payload()

    for body in (
        {**valid, "name": ""},
        {**valid, "interval_seconds": 4},
        {**valid, "failure_threshold": 11},
        {**valid, "url": "not-a-url"},
        {**valid, "extra": "not allowed"},
        {**valid, "owner_id": str(uuid4())},
    ):
        response = await monitoring.post("/monitors", json=body, headers=headers)
        assert response.status_code == 422, (body, response.text)
