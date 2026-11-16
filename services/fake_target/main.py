"""Local test target: ALL endpoints are intentionally unimplemented."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from .schemas import Mode

app = FastAPI(title="SignalWatch Fake Target", version="1.0.0")


@app.get("/health", response_class=JSONResponse)
async def health() -> JSONResponse:
    ...


@app.get("/__test__/state", response_model=Mode)
async def get_mode() -> Mode:
    ...


@app.post("/__test__/mode", response_model=Mode)
async def set_mode(body: Mode) -> Mode:
    ...


@app.post("/__test__/reset", response_model=Mode)
async def reset_mode() -> Mode:
    ...
