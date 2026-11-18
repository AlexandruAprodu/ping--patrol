from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

def create_async_session_maker(db_url):
    engine = create_async_engine(db_url)

    AsyncSessionMakerLocal = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )
    return AsyncSessionMakerLocal
