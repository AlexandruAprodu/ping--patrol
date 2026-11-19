from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest

from common import health as health_module
from services.users.constants import JWT_ALGORITHM, ROLE_ADMIN
from services.users.security import JWT_SECRET


pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def health_report():
    return {
        "status": "healthy",
        "checked_at": "2026-11-19T10:00:00Z",
        "services": {"monitoring": {"status": "up", "error": None}, "users": {"status": "up", "error": None}},
        "databases": {"monitoring": {"status": "up", "error": None}},
        "infrastructure": {"redis": {"status": "up", "error": None}},
    }


async def test_admin_receives_healthy_infrastructure_report(clients, authenticated_headers, health_report, monkeypatch):
    _, monitoring, _ = clients
    headers = await authenticated_headers(ROLE_ADMIN)
    check = AsyncMock(return_value=health_report)
    monkeypatch.setattr(health_module, "check_infrastructure", check)

    response = await monitoring.get("/health", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json() == health_report
    check.assert_awaited_once_with()


@pytest.mark.parametrize("section,component", [
    ("services", "users"), ("databases", "monitoring"), ("infrastructure", "redis"),
])
async def test_admin_receives_503_when_any_group_is_unhealthy(
    clients, authenticated_headers, health_report, monkeypatch, section, component,
):
    _, monitoring, _ = clients
    headers = await authenticated_headers(ROLE_ADMIN)
    health_report["status"] = "unhealthy"
    health_report[section][component] = {"status": "down", "error": "connection_failed"}
    check = AsyncMock(return_value=health_report)
    monkeypatch.setattr(health_module, "check_infrastructure", check)

    response = await monitoring.get("/health", headers=headers)

    assert response.status_code == 503, response.text
    assert isinstance(response.json()["detail"], str)
    check.assert_awaited_once_with()


async def test_regular_user_cannot_run_infrastructure_checks(clients, authenticated_headers, monkeypatch):
    _, monitoring, _ = clients
    headers = await authenticated_headers()
    check = AsyncMock()
    monkeypatch.setattr(health_module, "check_infrastructure", check)

    response = await monitoring.get("/health", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Page not found!"}
    check.assert_not_awaited()


@pytest.mark.parametrize("credentials", ["missing", "malformed", "expired"])
async def test_health_requires_a_valid_access_token(clients, monkeypatch, credentials):
    _, monitoring, _ = clients
    headers = {}
    if credentials == "malformed":
        headers["access_token"] = "invalid-token"
    elif credentials == "expired":
        now = datetime.now(timezone.utc)
        headers["access_token"] = jwt.encode(
            {"sub": str(uuid4()), "type": "access_token", "iat": now - timedelta(minutes=2), "exp": now - timedelta(minutes=1)},
            JWT_SECRET, algorithm=JWT_ALGORITHM,
        )
    check = AsyncMock()
    monkeypatch.setattr(health_module, "check_infrastructure", check)

    response = await monitoring.get("/health", headers=headers)

    assert response.status_code == 401
    check.assert_not_awaited()
