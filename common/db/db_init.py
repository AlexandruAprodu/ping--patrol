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
SERVICES_DIR = PROJECT_ROOT / "services"

if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT_ROOT))


def discover_services() -> list[str]:
    return sorted(
        path.name
        for path in SERVICES_DIR.iterdir()
        if path.is_dir() and path.name.isidentifier() and not path.name.startswith("_")
    )


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
    if not configured_url and (SERVICES_DIR / service / "constants.py").is_file():
        constants = import_module(f"services.{service}.constants")
        configured_url = getattr(constants, "DATABASE_URL", None)
    if configured_url:
        url = make_url(configured_url)
    else:
        url = URL.create(
            drivername="postgresql+asyncpg",
            username=os.environ.get("POSTGRES_USER", "ping_user"),
            password=os.environ.get("POSTGRES_PASSWORD", "secret123"),
            host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            database=os.environ.get(f"{service.upper()}_DB_NAME", f"ping_{service}"),
        )

    if url.drivername != "postgresql+asyncpg" or not url.database:
        raise ValueError(f"{service}: expected a postgresql+asyncpg URL with a database name")
    return url


async def init_database(service: str) -> None:
    if service not in discover_services():
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
            if database_exists:
                print(f"[{service}] Database already exists: {url.database}; skipped.")
                return
            database_name = connection.dialect.identifier_preparer.quote_identifier(url.database)
            await connection.exec_driver_sql(f"CREATE DATABASE {database_name}")
    finally:
        await admin_engine.dispose()

    print(f"[{service}] Database created: {url.database}")
    if not (SERVICES_DIR / service / "models.py").is_file():
        return
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


async def init_databases() -> None:
    load_env()
    for service in discover_services():
        await init_database(service)


def main() -> None:
    asyncio.run(init_databases())


if __name__ == "__main__":
    main()
