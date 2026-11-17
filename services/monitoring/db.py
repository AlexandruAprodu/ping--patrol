from common.db.session import create_async_session_maker
from services.monitoring.constants import DATABASE_URL


async def get_db():
    """Return the db needed by the current operation.
    Resolve it from the configured state or backing dependency.
    """
    async with create_async_session_maker(db_url=DATABASE_URL) as session:
        yield session
