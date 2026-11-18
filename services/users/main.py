from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import engine
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Ping Patrol Users", lifespan=lifespan)
app.include_router(router, prefix="/api/v1/auth", tags=["Authentication"])
