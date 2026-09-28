"""Procrastinate application and the demo task.

Procrastinate 3.x recommends ``PsycopgConnector`` (async, psycopg v3).
There is no asyncpg connector — use the IPv6-safe kwargs from ``app.db``
so the worker and the API hit Railway private Postgres on IPv6 first.
"""

from __future__ import annotations

import asyncio
import logging

from procrastinate import App, PsycopgConnector

from app.db import psycopg_kwargs, resolve_target
from app.settings import get_settings

log = logging.getLogger(__name__)

MAX_DEMO_SECONDS = 30.0


def build_app() -> App:
    """Build the App without resolving DNS.

    Railway private DNS can be empty for a few seconds after boot. Bind the
    IPv6-safe connector in ``bind_database()`` immediately before ``open_async``.
    """
    return App(connector=PsycopgConnector(), import_paths=["app.tasks"])


procrastinate_app = build_app()


def bind_database(app: App | None = None) -> App:
    """Resolve ``*.railway.internal`` (IPv6-first) and attach the connector."""
    target_app = app or procrastinate_app
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set")
    target = resolve_target()
    connector = PsycopgConnector(kwargs=psycopg_kwargs(target))
    target_app.connector = connector
    target_app.job_manager.connector = connector
    return target_app


@procrastinate_app.task(name="app.tasks.demo_sleep", queue="demo")
async def demo_sleep(seconds: float = 2.0, message: str = "demo") -> dict[str, object]:
    """Short sleep + log job. Enqueued by ``POST /jobs/demo``."""
    delay = max(0.0, min(float(seconds), MAX_DEMO_SECONDS))
    log.info("demo job started message=%s seconds=%s", message, delay)
    await asyncio.sleep(delay)
    log.info("demo job finished message=%s", message)
    return {"message": message, "slept": delay}


def rebuild_app() -> App:
    """Rebuild after DATABASE_URL is known (tests / late env)."""
    global procrastinate_app
    procrastinate_app = build_app()
    if get_settings().database_url:
        bind_database(procrastinate_app)
    return procrastinate_app
