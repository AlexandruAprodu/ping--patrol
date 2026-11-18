from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .constants import DATABASE_URL

engine = create_async_engine(DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db():
    async with SessionLocal() as session:
        yield session
