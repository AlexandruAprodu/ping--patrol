"""Unit tests for the shared infrastructure probes and Monitoring health schema."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from common import health as health_module
from services.monitoring.schemas import HealthResponse


def test_health_response_accepts_dynamic_services_and_databases():
    report = {
        "status": "unhealthy",
        "checked_at": "2026-11-19T13:00:00Z",
        "services": {
            "monitoring": {"status": "up", "error": None},
            "c6": {"status": "down", "error": "connection_failed"},
        },
        "databases": {"c6": {"status": "up", "error": None}},
        "infrastructure": {"redis": {"status": "up", "error": None}},
    }

    model = HealthResponse.model_validate(report)

    assert model.services["c6"].status == "down"
    assert model.checked_at.tzinfo is not None
    assert model.model_dump(mode="json")["services"]["c6"]["error"] == "connection_failed"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report.update(status="ok"),
        lambda report: report["services"]["monitoring"].update(status="unknown"),
        lambda report: report["services"]["monitoring"].update(error="password=secret"),
        lambda report: report.update(unexpected="extra"),
        lambda report: report.pop("infrastructure"),
    ],
)
def test_health_response_rejects_invalid_contract(mutation):
    report = {
        "status": "healthy",
        "checked_at": datetime.now(timezone.utc),
        "services": {"monitoring": {"status": "up", "error": None}},
        "databases": {},
        "infrastructure": {},
    }
    mutation(report)
    with pytest.raises(ValidationError):
        HealthResponse.model_validate(report)


@pytest.mark.asyncio
async def test_guard_reports_success_failure_and_deadline():
    async def succeeds():
        return None

    async def fails():
        raise OSError("private connection string")

    async def hangs():
        await asyncio.Event().wait()

    assert await health_module._guard(succeeds, 0.1) == {"status": "up", "error": None}
    assert await health_module._guard(fails, 0.1) == {
        "status": "down", "error": "connection_failed"
    }
    assert await health_module._guard(hangs, 0.01) == {
        "status": "down", "error": "timeout"
    }


def test_http_ports_parses_launcher_and_ignores_comments(tmp_path, monkeypatch):
    (tmp_path / "start_servers.sh").write_text(
        "start_http monitoring services.monitoring.main 8001\n"
        "start_http c6 services.c6.main 9016\n"
        "#start_http stopped services.stopped.main 7000\n"
        "start_http invalid other.invalid.main 9999\n"
    )
    monkeypatch.setattr(health_module, "PROJECT_ROOT", tmp_path)

    assert health_module._http_ports() == {"monitoring": 8001, "c6": 9016}


@pytest.mark.asyncio
async def test_http_check_accepts_tcp_connection_without_http_or_jwt():
    async def accept_then_close(reader, writer):
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(accept_then_close, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        await health_module._check_http_service(port, timeout=0.5)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_report_discovers_new_services_and_checks_all_dependencies(tmp_path, monkeypatch):
    for service in ("monitoring", "c6"):
        folder = tmp_path / service
        folder.mkdir()
        (folder / "main.py").touch()
        (folder / "db.py").touch()

    checked_db = []
    checked_ports = []

    async def check_db(service, timeout):
        checked_db.append(service)

    async def check_http(port, timeout):
        checked_ports.append(port)

    monkeypatch.setattr(health_module, "SERVICES_DIR", tmp_path)
    monkeypatch.setattr(health_module, "load_env", lambda: None)
    monkeypatch.setattr(health_module, "discover_services", lambda: ["monitoring", "c6"])
    monkeypatch.setattr(health_module, "_http_ports", lambda: {"monitoring": 8001, "c6": 9016})
    monkeypatch.setattr(health_module, "_check_database", check_db)
    monkeypatch.setattr(health_module, "_check_http_service", check_http)
    monkeypatch.setattr(health_module, "_check_redis", AsyncMock())
    monkeypatch.setattr(health_module, "_check_rabbitmq_sync", lambda timeout: None)
    monkeypatch.setattr(health_module, "_check_celery_sync", lambda timeout: None)

    report = await health_module.check_infrastructure(timeout=0.5)

    assert report["status"] == "healthy"
    assert set(report["services"]) == {"monitoring", "c6"}
    assert set(report["databases"]) == {"monitoring", "c6"}
    assert set(report["infrastructure"]) == {"rabbitmq", "redis", "celery"}
    assert set(checked_db) == {"monitoring", "c6"}
    assert set(checked_ports) == {8001, 9016}
    assert all(
        dependency == {"status": "up", "error": None}
        for section in ("services", "databases", "infrastructure")
        for dependency in report[section].values()
    )
    HealthResponse.model_validate(report)


@pytest.mark.asyncio
async def test_report_keeps_all_results_when_a_probe_fails_or_port_is_missing(tmp_path, monkeypatch):
    for name in ("monitoring", "c6"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "main.py").touch()
        (folder / "db.py").touch()

    async def check_db(name, timeout):
        if name == "c6":
            raise ConnectionError("db unavailable")

    async def check_http(port, timeout):
        pass

    async def check_redis(timeout):
        await asyncio.Event().wait()

    monkeypatch.setattr(health_module, "SERVICES_DIR", tmp_path)
    monkeypatch.setattr(health_module, "load_env", lambda: None)
    monkeypatch.setattr(health_module, "discover_services", lambda: ["monitoring", "c6"])
    monkeypatch.setattr(health_module, "_http_ports", lambda: {"monitoring": 8001})
    monkeypatch.setattr(health_module, "_check_database", check_db)
    monkeypatch.setattr(health_module, "_check_http_service", check_http)
    monkeypatch.setattr(health_module, "_check_redis", check_redis)
    monkeypatch.setattr(health_module, "_check_rabbitmq_sync", lambda timeout: None)
    monkeypatch.setattr(health_module, "_check_celery_sync", lambda timeout: None)

    report = await health_module.check_infrastructure(timeout=0.2)

    assert report["status"] == "unhealthy"
    assert report["services"]["monitoring"]["status"] == "up"
    assert report["services"]["c6"] == {"status": "down", "error": "not_configured"}
    assert report["databases"]["c6"] == {"status": "down", "error": "connection_failed"}
    assert report["infrastructure"]["redis"] == {"status": "down", "error": "timeout"}
    assert report["infrastructure"]["rabbitmq"]["status"] == "up"
    assert report["infrastructure"]["celery"]["status"] == "up"
    HealthResponse.model_validate(report)


def test_celery_probe_requires_pong_from_a_worker(monkeypatch):
    class FakeApp:
        def __init__(self, *args, **kwargs):
            self.conf = self
            self.control = self
            self.replies = None
            self.closed = False

        def update(self, **kwargs):
            pass

        def inspect(self, timeout):
            return self

        def ping(self):
            return self.replies

        def close(self):
            self.closed = True

    fake = FakeApp()
    monkeypatch.setattr(health_module, "Celery", lambda *args, **kwargs: fake)
    with pytest.raises(ConnectionError, match="No Celery worker replied"):
        health_module._check_celery_sync(0.1)
    assert fake.closed

    fake.replies = {"celery@worker": {"ok": "pong"}}
    health_module._check_celery_sync(0.1)
    assert fake.closed
