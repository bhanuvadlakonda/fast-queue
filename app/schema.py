"""Idempotent Procrastinate schema apply for first deploy.

``procrastinate schema --apply`` installs the full schema and errors if the
tables already exist. This wrapper checks for ``procrastinate_jobs``, then
applies once under an advisory lock so API pre-deploy and the worker do not
race on first boot.
"""

from __future__ import annotations

import logging

import asyncpg
from procrastinate import App

from app.db import asyncpg_kwargs, resolve_target

log = logging.getLogger(__name__)

SCHEMA_LOCK_ID = 726_331_912


async def _connect() -> asyncpg.Connection:
    target = resolve_target()
    kwargs = asyncpg_kwargs(target)
    return await asyncpg.connect(**kwargs)


async def jobs_table_exists(conn: asyncpg.Connection) -> bool:
    present = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = 'procrastinate_jobs'
        )
        """
    )
    return bool(present)


async def ensure_schema(app: App) -> str:
    conn = await _connect()
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", SCHEMA_LOCK_ID)
        try:
            if await jobs_table_exists(conn):
                log.info("Procrastinate schema already present")
                return "present"
            log.info("Applying Procrastinate schema")
            await app.schema_manager.apply_schema_async()
            log.info("Procrastinate schema applied")
            return "applied"
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", SCHEMA_LOCK_ID)
    finally:
        await conn.close()
