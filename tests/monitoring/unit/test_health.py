import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from common import health


pytestmark = pytest.mark.asyncio


@pytest.fixture
def isolated_checks(monkeypatch, tmp_path):
    for name in ("monitoring", "users"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "db.py").touch()
        (folder / "main.py").touch()
    monkeypatch.setattr(health, "SERVICES_DIR", tmp_path)
    monkeypatch.setattr(health, "load_env", lambda: None)
    monkeypatch.setattr(health, "discover_services", lambda: ["monitoring", "users"])
    monkeypatch.setattr(health, "_http_ports", lambda: {"monitoring": 8001, "users": 8005})
    checks = {
        "_check_database": AsyncMock(),
        "_check_http_service": AsyncMock(),
        "_check_redis": AsyncMock(),
        "_check_rabbitmq_sync": Mock(),
        "_check_celery_sync": Mock(),
    }
    for name, check in checks.items():
        monkeypatch.setattr(health, name, check)
    return checks


def assert_all_components_checked(checks):
    assert checks["_check_database"].await_count == 2
    assert checks["_check_http_service"].await_count == 2
    checks["_check_redis"].assert_awaited_once()
    checks["_check_rabbitmq_sync"].assert_called_once()
    checks["_check_celery_sync"].assert_called_once()


async def test_healthy_report_contains_services_databases_and_infrastructure(isolated_checks):
    report = await health.check_infrastructure()

    assert report["status"] == "healthy"
    assert datetime.fromisoformat(report["checked_at"]).utcoffset().total_seconds() == 0
    assert set(report["services"]) == {"monitoring", "users"}
    assert set(report["databases"]) == {"monitoring", "users"}
    assert set(report["infrastructure"]) == {"redis", "rabbitmq", "celery"}
    for section in ("services", "databases", "infrastructure"):
        assert all(result == {"status": "up", "error": None} for result in report[section].values())
    assert_all_components_checked(isolated_checks)


@pytest.mark.parametrize("check_name,section,component", [
    ("_check_database", "databases", "monitoring"),
    ("_check_http_service", "services", "users"),
    ("_check_redis", "infrastructure", "redis"),
    ("_check_rabbitmq_sync", "infrastructure", "rabbitmq"),
    ("_check_celery_sync", "infrastructure", "celery"),
])
async def test_failure_is_sanitized_and_does_not_skip_other_checks(isolated_checks, check_name, section, component):
    isolated_checks[check_name].side_effect = ConnectionError("private-database-password")

    report = await health.check_infrastructure()

    assert report["status"] == "unhealthy"
    assert report[section][component] == {"status": "down", "error": "connection_failed"}
    assert "private-database-password" not in str(report)
    assert_all_components_checked(isolated_checks)


async def test_new_service_without_a_launch_port_is_reported_down(isolated_checks, monkeypatch, tmp_path):
    folder = tmp_path / "new_service"
    folder.mkdir()
    (folder / "main.py").touch()
    monkeypatch.setattr(health, "discover_services", lambda: ["monitoring", "users", "new_service"])

    report = await health.check_infrastructure()

    assert report["status"] == "unhealthy"
    assert report["services"]["new_service"] == {"status": "down", "error": "not_configured"}
    assert_all_components_checked(isolated_checks)


async def test_guard_times_out_a_check_that_never_finishes():
    async def blocked():
        await asyncio.Event().wait()

    result = await health._guard(blocked, timeout=0.01)

    assert result == {"status": "down", "error": "timeout"}
