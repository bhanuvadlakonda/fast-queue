"""FastAPI process: enqueue jobs and stay healthy before any job exists."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.web import INDEX_HTML

from app.jobs import fetch_job, list_jobs, ping
from app.schema import ensure_schema
from app.settings import get_settings
from app.tasks import MAX_DEMO_SECONDS, bind_database, demo_sleep, procrastinate_app

log = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_logging()
    settings = get_settings()
    if settings.database_url:
        try:
            bind_database(procrastinate_app)
            async with procrastinate_app.open_async():
                await ensure_schema(procrastinate_app)
                yield
        except Exception:
            log.exception("Database is not ready; API still serves /healthz")
            yield
    else:
        log.warning("DATABASE_URL unset — /healthz works, enqueue returns 503")
        yield


api = FastAPI(
    title="FastAPI + Procrastinate",
    description=(
        "Postgres-native job queue starter. POST /jobs/demo enqueues a short "
        "sleep job; the worker process drains it. No Redis."
    ),
    lifespan=lifespan,
)


class DemoJobIn(BaseModel):
    seconds: float = Field(default=2.0, ge=0, le=MAX_DEMO_SECONDS)
    message: str = Field(default="demo", max_length=200)


class DemoJobOut(BaseModel):
    id: int
    status: str
    queue: str
    task: str
    seconds: float
    message: str


class JobOut(BaseModel):
    id: int
    status: str
    queue_name: str
    task_name: str
    scheduled_at: datetime | None = None
    attempts: int | None = None


def _require_token(authorization: str | None) -> None:
    token = get_settings().job_api_token
    if not token:
        return
    expected = f"Bearer {token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


def _require_database() -> None:
    if not get_settings().database_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")


@api.get("/", response_class=HTMLResponse)
async def index() -> str:
    return INDEX_HTML


@api.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness. Always 200 so Railway can pass a healthcheck before jobs exist."""
    return {"status": "ok"}


@api.get("/readyz")
async def readyz() -> dict[str, Any]:
    _require_database()
    try:
        await ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc
    return {"status": "ready"}


@api.post("/jobs/demo", response_model=DemoJobOut)
async def enqueue_demo(
    body: DemoJobIn,
    authorization: str | None = Header(default=None),
) -> DemoJobOut:
    """Enqueue the demo sleep/log job. The worker process executes it."""
    _require_token(authorization)
    _require_database()
    try:
        job_id = await demo_sleep.defer_async(seconds=body.seconds, message=body.message)
    except Exception as exc:
        log.exception("Failed to enqueue demo job")
        raise HTTPException(status_code=503, detail=f"enqueue failed: {exc}") from exc
    return DemoJobOut(
        id=int(job_id),
        status="todo",
        queue="demo",
        task="app.tasks.demo_sleep",
        seconds=body.seconds,
        message=body.message,
    )


@api.get("/jobs", response_model=list[JobOut])
async def get_jobs(
    limit: int = Query(default=25, ge=1, le=100),
    authorization: str | None = Header(default=None),
) -> list[JobOut]:
    _require_token(authorization)
    _require_database()
    try:
        rows = await list_jobs(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"jobs query failed: {exc}") from exc
    return [JobOut.model_validate(row) for row in rows]


@api.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: int,
    authorization: str | None = Header(default=None),
) -> JobOut:
    _require_token(authorization)
    _require_database()
    row = await fetch_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobOut.model_validate(row)


app = api


def main() -> None:
    _configure_logging()
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    # Railway injects PORT. Do not bind :: — see README Station pitfalls.
    os.environ.setdefault("PORT", str(get_settings().port))
    main()
