"""HTTP integration tests for Monitoring /health with real Users auth and test PostgreSQL."""

from copy import deepcopy
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest

from common import health as health_module
from services.monitoring.schemas import HealthResponse
from services.users.constants import ROLE_ADMIN, ROLE_USER


pytestmark = pytest.mark.asyncio(loop_scope="session")


def healthy_report():
    up = {"status": "up", "error": None}
    return {
        "status": "healthy",
        "checked_at": "2026-11-19T13:00:00Z",
        "services": {
            "monitoring": dict(up),
            "alerts": dict(up),
            "c6": dict(up),
        },
        "databases": {"monitoring": dict(up), "c6": dict(up)},
        "infrastructure": {
            "rabbitmq": dict(up),
            "redis": dict(up),
            "celery": dict(up),
        },
    }


async def registered_user_headers(users, role=ROLE_USER):
    key = uuid4().hex[:14]
    credentials = {
        "email": f"{key}@example.com",
        "username": f"user_{key}",
        "password": "SafePassword123!",
    }
    registered = await users.post("/api/v1/auth/register/", json=credentials)
    assert registered.status_code == 201, registered.text
    user_id = UUID(registered.json()["id"])
    assert registered.json()["role"] == ROLE_USER

    if role != ROLE_USER:
        # Registration never allows client-controlled admin roles.
        from services.users.db import SessionLocal
        from services.users.models import User

        async with SessionLocal() as session:
            user = await session.get(User, user_id)
            assert user is not None
            user.role = role
            await session.commit()

    logged_in = await users.post(
        "/api/v1/auth/login",
        data={"username": credentials["username"], "password": credentials["password"]},
    )
    assert logged_in.status_code == 200, logged_in.text
    return {"access_token": logged_in.json()["access_token"]}


async def test_health_admin_receives_200_and_complete_dynamic_report(clients, monkeypatch):
    users, monitoring, _ = clients
    headers = await registered_user_headers(users, ROLE_ADMIN)
    report = healthy_report()
    probe = AsyncMock(return_value=deepcopy(report))
    monkeypatch.setattr(health_module, "check_infrastructure", probe)

    response = await monitoring.get("/health", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == report
    assert HealthResponse.model_validate(response.json()).services["c6"].status == "up"
    probe.assert_awaited_once_with()


@pytest.mark.parametrize("section,name", [
    ("services", "alerts"),
    ("databases", "c6"),
    ("infrastructure", "rabbitmq"),
])
async def test_health_admin_receives_503_when_any_component_is_down(
    clients, monkeypatch, section, name
):
    users, monitoring, _ = clients
    headers = await registered_user_headers(users, ROLE_ADMIN)
    report = healthy_report()
    report["status"] = "unhealthy"
    report[section][name] = {"status": "down", "error": "connection_failed"}
    probe = AsyncMock(return_value=report)
    monkeypatch.setattr(health_module, "check_infrastructure", probe)

    response = await monitoring.get("/health", headers=headers)

    assert response.status_code == 503, response.text
    assert response.json()["detail"].startswith("Services unhealthy:")
    if section == "services":
        assert name in response.json()["detail"]
    probe.assert_awaited_once_with()


async def test_health_non_admin_is_404_and_does_not_check_infrastructure(clients, monkeypatch):
    users, monitoring, _ = clients
    headers = await registered_user_headers(users)
    probe = AsyncMock(return_value=healthy_report())
    monkeypatch.setattr(health_module, "check_infrastructure", probe)

    response = await monitoring.get("/health", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Page not found!"}
    probe.assert_not_awaited()


@pytest.mark.parametrize("headers", [{}, {"access_token": "invalid.jwt.token"}])
async def test_health_requires_valid_jwt_and_skips_checks(clients, monkeypatch, headers):
    _, monitoring, _ = clients
    probe = AsyncMock(return_value=healthy_report())
    monkeypatch.setattr(health_module, "check_infrastructure", probe)

    response = await monitoring.get("/health", headers=headers)

    assert response.status_code == 401
    probe.assert_not_awaited()
