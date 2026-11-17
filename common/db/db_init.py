"""Create a service's PostgreSQL database and its SQLAlchemy tables.

Usage: python -m common.db.db_init <monitoring|rules|incidents|alerts|fake_target>
"""

from __future__ import annotations

import asyncio
import os
import sys
from importlib import import_module
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVICES = frozenset({"monitoring", "rules", "incidents", "alerts", "fake_target"})


def load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key.isidentifier():
            os.environ.setdefault(key, value)


def get_database_url(service: str) -> URL:
    configured_url = os.environ.get(f"{service.upper()}_DATABASE_URL")
    if configured_url:
        url = make_url(configured_url)
    else:
        url = URL.create(
            drivername="postgresql+asyncpg",
            username=os.environ.get("POSTGRES_USER", "poc"),
            password=os.environ.get("POSTGRES_PASSWORD", "local_development_only"),
            host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            database=os.environ.get(f"{service.upper()}_DB_NAME", f"ping_{service}"),
        )

    if url.drivername != "postgresql+asyncpg" or not url.database:
        raise ValueError(f"{service}: expected a postgresql+asyncpg URL with a database name")
    return url


async def init_database(service: str) -> None:
    if service not in SERVICES:
        raise ValueError(f"Unknown microservice: {service}")

    load_env()
    url = get_database_url(service)

    # PostgreSQL CREATE DATABASE must run with autocommit.
    admin_engine = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin_engine.connect() as connection:
            database_exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": url.database},
            )
            if not database_exists:
                database_name = connection.dialect.identifier_preparer.quote_identifier(url.database)
                await connection.exec_driver_sql(f"CREATE DATABASE {database_name}")
    finally:
        await admin_engine.dispose()

    # Import only the chosen service's model module.
    models = import_module(f"services.{service}.models")
    base = getattr(models, "Base", None)
    if base is None:
        from common.db.base import Base
        base = Base

    if not base.metadata.tables:
        raise RuntimeError(f"No SQLAlchemy models found for {service}")

    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(base.metadata.create_all)
    finally:
        await engine.dispose()

    print(f"[{service}] Database: {url.database}")
    print(f"[{service}] Tables: {', '.join(sorted(base.metadata.tables))}")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in SERVICES:
        raise SystemExit(
            "Usage: python -m common.db.db_init "
            "<monitoring|rules|incidents|alerts|fake_target>"
        )
    asyncio.run(init_database(sys.argv[1]))


if __name__ == "__main__":
    main()
