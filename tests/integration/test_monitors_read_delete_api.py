"""PostgreSQL-backed API tests for MON-03 monitor listing, retrieval and deletion."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from services.monitoring.models import MonitorModel


pytestmark = pytest.mark.asyncio(loop_scope="session")


async def authorized_user(users):
    unique = uuid4().hex[:14]
    registration = {
        "email": f"{unique}@example.com",
        "username": f"user_{unique}",
        "password": "SafePassword123!",
    }
    response = await users.post("/api/v1/auth/register/", json=registration)
    assert response.status_code == 201, response.text

    login = await users.post(
        "/api/v1/auth/login",
        data={"username": registration["username"], "password": registration["password"]},
    )
    assert login.status_code == 200, login.text
    return UUID(response.json()["id"]), {"access_token": login.json()["access_token"]}


async def insert_monitor(monitoring, headers, name="Example"):
    payload = {
        "name": name,
        "url": f"https://{uuid4().hex}.example.org/health",
        "interval_seconds": 60,
        "failure_threshold": 3,
    }
    response = await monitoring.post("/monitors", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def safe_request(method, path, headers):
    """Return 500 as an HTTP response when the app raises, instead of masking the status with ASGITransport exceptions."""
    from services.monitoring.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://localhost:8001",
    ) as client:
        return await client.request(method, path, headers=headers)


async def test_list_monitors_returns_empty_list_for_new_user(clients):
    users, monitoring, _ = clients
    _, headers = await authorized_user(users)

    response = await monitoring.get("/monitors", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_list_monitors_is_owner_scoped_and_sorted_newest_first(clients):
    users, monitoring, engine = clients
    owner_a, headers_a = await authorized_user(users)
    owner_b, headers_b = await authorized_user(users)

    first = await insert_monitor(monitoring, headers_a, "First")
    second = await insert_monitor(monitoring, headers_a, "Second")
    third = await insert_monitor(monitoring, headers_a, "Third")
    foreign = await insert_monitor(monitoring, headers_b, "Other user's monitor")

    # Assign distinct timestamps to make ordering deterministic even on fast CI runners.
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with async_sessionmaker(engine)() as session:
        for item, timestamp in (
            (first, base),
            (second, base + timedelta(days=1)),
            (third, base + timedelta(days=2)),
        ):
            await session.execute(
                update(MonitorModel)
                .where(MonitorModel.id == UUID(item["id"]))
                .values(created_at=timestamp)
            )
        await session.commit()

    response = await monitoring.get("/monitors", headers=headers_a)

    assert response.status_code == 200, response.text
    rows = response.json()
    assert isinstance(rows, list)
    assert [row["id"] for row in rows] == [
        third["id"], second["id"], first["id"]
    ]
    assert all(UUID(row["id"]) for row in rows)
    assert all(row["created_at"] for row in rows)
    assert foreign["id"] not in {row["id"] for row in rows}
    assert {row["name"] for row in rows} == {"First", "Second", "Third"}

    other_response = await monitoring.get("/monitors", headers=headers_b)
    assert other_response.status_code == 200
    assert [row["id"] for row in other_response.json()] == [foreign["id"]]


async def test_list_monitors_requires_valid_jwt(clients):
    _, monitoring, _ = clients
    assert (await monitoring.get("/monitors")).status_code == 401
    assert (
        await monitoring.get("/monitors", headers={"access_token": "invalid"})
    ).status_code == 401


async def test_get_monitor_returns_exact_record_for_its_owner(clients):
    users, monitoring, _ = clients
    _, headers = await authorized_user(users)
    created = await insert_monitor(monitoring, headers, "Details")

    response = await monitoring.get(f"/monitors/{created['id']}", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == created


async def test_get_monitor_other_owner_returns_404(clients):
    users, monitoring, _ = clients
    _, owner_headers = await authorized_user(users)
    _, stranger_headers = await authorized_user(users)
    monitor = await insert_monitor(monitoring, owner_headers)

    response = await safe_request("GET", f"/monitors/{monitor['id']}", stranger_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Monitor not found!"


async def test_get_monitor_unknown_uuid_returns_404(clients):
    users, _, _ = clients
    _, headers = await authorized_user(users)

    response = await safe_request("GET", f"/monitors/{uuid4()}", headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Monitor not found!"


async def test_get_monitor_invalid_uuid_returns_422(clients):
    users, monitoring, _ = clients
    _, headers = await authorized_user(users)

    response = await monitoring.get("/monitors/not-a-uuid", headers=headers)

    assert response.status_code == 422


async def test_get_monitor_requires_valid_jwt(clients):
    users, monitoring, _ = clients
    _, headers = await authorized_user(users)
    monitor = await insert_monitor(monitoring, headers)
    path = f"/monitors/{monitor['id']}"

    assert (await monitoring.get(path)).status_code == 401
    assert (await monitoring.get(path, headers={"access_token": "invalid"})).status_code == 401


async def test_delete_monitor_returns_204_and_removes_database_row(clients):
    users, monitoring, engine = clients
    owner_id, headers = await authorized_user(users)
    monitor = await insert_monitor(monitoring, headers)

    response = await monitoring.delete(f"/monitors/{monitor['id']}", headers=headers)

    assert response.status_code == 204, response.text
    assert response.content == b""

    async with async_sessionmaker(engine)() as session:
        assert await session.get(MonitorModel, UUID(monitor["id"])) is None

    listing = await monitoring.get("/monitors", headers=headers)
    assert listing.status_code == 200, listing.text
    assert monitor["id"] not in {row["id"] for row in listing.json()}


async def test_delete_monitor_other_owner_returns_404_and_preserves_record(clients):
    users, monitoring, engine = clients
    owner_id, owner_headers = await authorized_user(users)
    _, stranger_headers = await authorized_user(users)
    monitor = await insert_monitor(monitoring, owner_headers)

    response = await safe_request("DELETE", f"/monitors/{monitor['id']}", stranger_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Monitor not found!"

    async with async_sessionmaker(engine)() as session:
        row = await session.get(MonitorModel, UUID(monitor["id"]))
        assert row is not None
        assert row.owner_id == owner_id


async def test_delete_monitor_unknown_uuid_returns_404(clients):
    users, _, _ = clients
    _, headers = await authorized_user(users)

    response = await safe_request("DELETE", f"/monitors/{uuid4()}", headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Monitor not found!"


async def test_delete_monitor_invalid_uuid_returns_422(clients):
    users, monitoring, _ = clients
    _, headers = await authorized_user(users)

    response = await monitoring.delete("/monitors/not-a-uuid", headers=headers)

    assert response.status_code == 422


async def test_delete_monitor_requires_valid_jwt(clients):
    users, monitoring, engine = clients
    _, headers = await authorized_user(users)
    monitor = await insert_monitor(monitoring, headers)
    path = f"/monitors/{monitor['id']}"

    assert (await monitoring.delete(path)).status_code == 401
    assert (await monitoring.delete(path, headers={"access_token": "invalid"})).status_code == 401

    async with async_sessionmaker(engine)() as session:
        assert await session.get(MonitorModel, UUID(monitor["id"])) is not None
