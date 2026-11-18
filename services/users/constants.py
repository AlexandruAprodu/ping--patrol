import os

from sqlalchemy.engine import URL

from common.db.db_init import load_env

load_env()
DATABASE_URL = os.getenv("USERS_DATABASE_URL") or URL.create(
    "postgresql+asyncpg",
    username=os.getenv("POSTGRES_USER", "ping_user"),
    password=os.getenv("POSTGRES_PASSWORD", "secret123"),
    host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    database=os.getenv("USERS_DB_NAME", "ping_users"),
)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN = "access_token"
REFRESH_TOKEN = "refresh_token"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "4320"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
REFRESH_TOKEN_COOKIE_NAME = "ping_patrol_refresh_token"
REFRESH_TOKEN_COOKIE_PATH = "/api/v1/auth"
REFRESH_TOKEN_COOKIE_SECURE = os.getenv("REFRESH_TOKEN_COOKIE_SECURE", "false").lower() in {"1", "true", "yes"}
REFRESH_TOKEN_COOKIE_SAMESITE = "lax"
