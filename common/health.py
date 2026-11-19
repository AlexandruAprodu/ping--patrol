from __future__ import annotations

import asyncio
import os
import shlex
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from celery import Celery
from kombu import Connection
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from common.db.db_init import (
    PROJECT_ROOT,
    SERVICES_DIR,
    discover_services,
    get_database_url,
    load_env,
)


def _result(up: bool, error: str | None = None) -> dict:
    return {"status": "up" if up else "down", "error": error}


async def _guard(check: Callable[[], Awaitable[None]], timeout: float) -> dict:
    try:
        async with asyncio.timeout(timeout):
            await check()
        return _result(True)
    except TimeoutError:
        return _result(False, "timeout")
    except Exception:
        return _result(False, "connection_failed")


def _http_ports() -> dict[str, int]:
    """Discover launch ports from the project's start_servers.sh."""
    ports = {}
    for line in (PROJECT_ROOT / "start_servers.sh").read_text().splitlines():
        try:
            args = shlex.split(line, comments=True)
        except ValueError:
            continue
        if len(args) != 4 or args[0] != "start_http":
            continue
        _, _, module, port = args
        parts = module.split(".")
        if len(parts) == 3 and parts[0] == "services" and parts[2] == "main":
            try:
                ports[parts[1]] = int(port)
            except ValueError:
                pass
    return ports


def _rabbitmq_url() -> str:
    if url := os.getenv("RABBITMQ_URL"):
        return url
    user = quote(os.getenv("RABBITMQ_USER", "guest"), safe="")
    password = quote(os.getenv("RABBITMQ_PASSWORD", "guest"), safe="")
    port = os.getenv("RABBITMQ_PORT", "5672")
    return f"amqp://{user}:{password}@127.0.0.1:{port}//"


def _redis_url() -> str:
    if url := os.getenv("REDIS_URL"):
        return url
    backend = os.getenv("CELERY_RESULT_BACKEND", "")
    if backend.startswith(("redis://", "rediss://")):
        return backend
    return f"redis://127.0.0.1:{os.getenv('REDIS_PORT', '6379')}/0"


async def _check_database(service: str, timeout: float) -> None:
    url = get_database_url(service)
    engine = create_async_engine(
        url, poolclass=NullPool, connect_args={"timeout": timeout}
    )
    try:
        async with engine.connect() as conn:
            if await conn.scalar(text("SELECT 1")) != 1:
                raise ConnectionError("Database did not respond to SELECT 1")
    finally:
        await engine.dispose()


async def _check_http_service(port: int, timeout: float) -> None:
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", port),
        timeout=timeout,
    )

    try:
        pass
    finally:
        writer.close()
        await writer.wait_closed()


async def _check_redis(timeout: float) -> None:
    client = Redis.from_url(
        _redis_url(), socket_connect_timeout=timeout, socket_timeout=timeout
    )
    try:
        if not await client.ping():
            raise ConnectionError("Redis did not respond to PING")
    finally:
        await client.aclose()


def _check_rabbitmq_sync(timeout: float) -> None:
    with Connection(_rabbitmq_url(), connect_timeout=timeout) as connection:
        connection.connect()
        channel = connection.channel()
        channel.close()


def _check_celery_sync(timeout: float) -> None:
    # Uses the same Celery broker as start_dependencies.sh.
    app = Celery(
        "ping_patrol_health",
        broker=os.getenv("CELERY_BROKER_URL") or _rabbitmq_url(),
    )
    app.conf.update(
        broker_connection_timeout=timeout,
        broker_connection_retry=False,
    )
    try:
        replies = app.control.inspect(timeout=timeout).ping()
        if not replies or not any(
            isinstance(reply, dict) and reply.get("ok") == "pong"
            for reply in replies.values()
        ):
            raise ConnectionError("No Celery worker replied")
    finally:
        app.close()


async def check_infrastructure(timeout: float = 2.0) -> dict:
    """Discover local HTTP services and their PostgreSQL databases."""
    load_env()
    names = discover_services()
    ports = _http_ports()
    checks: dict[tuple[str, str], Awaitable[dict]] = {}

    for name in names:
        folder = SERVICES_DIR / name

        if (folder / "db.py").is_file():
            checks[("databases", name)] = _guard(
                lambda n=name: _check_database(n, timeout), timeout
            )

        if (folder / "main.py").is_file() and name in ports:
            checks[("services", name)] = _guard(
                lambda p=ports[name]: _check_http_service(p, timeout),
                timeout,
            )

    checks[("infrastructure", "redis")] = _guard(
        lambda: _check_redis(timeout), timeout
    )
    checks[("infrastructure", "rabbitmq")] = _guard(
        lambda: asyncio.to_thread(_check_rabbitmq_sync, timeout), timeout
    )
    checks[("infrastructure", "celery")] = _guard(
        lambda: asyncio.to_thread(_check_celery_sync, timeout), 2 * timeout
    )

    results = await asyncio.gather(*checks.values())
    report: dict[str, dict] = {
        "services": {},
        "databases": {},
        "infrastructure": {},
    }
    for (section, name), result in zip(checks, results):
        report[section][name] = result

    # A new service without a launch port is discovered, not silently skipped.
    for name in names:
        if (SERVICES_DIR / name / "main.py").is_file() and name not in ports:
            report["services"][name] = _result(False, "not_configured")

    healthy = all(
        item["status"] == "up"
        for section in report.values()
        for item in section.values()
    )
    return {
        "status": "healthy" if healthy else "unhealthy",
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **report,
    }
