"""Read Procrastinate job rows through the IPv6-safe asyncpg helper."""

from __future__ import annotations

from typing import Any

import asyncpg

from app.db import asyncpg_kwargs, resolve_target


async def fetch_job(job_id: int) -> dict[str, Any] | None:
    conn = await asyncpg.connect(**asyncpg_kwargs(resolve_target()))
    try:
        row = await conn.fetchrow(
            """
            SELECT id, status, queue_name, task_name, scheduled_at,
                   attempts, scheduled_at AS created_hint
            FROM procrastinate_jobs
            WHERE id = $1
            """,
            job_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def list_jobs(limit: int = 25) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(**asyncpg_kwargs(resolve_target()))
    try:
        rows = await conn.fetch(
            """
            SELECT id, status, queue_name, task_name, scheduled_at, attempts
            FROM procrastinate_jobs
            ORDER BY id DESC
            LIMIT $1
            """,
            limit,
        )
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def ping() -> bool:
    conn = await asyncpg.connect(**asyncpg_kwargs(resolve_target()))
    try:
        value = await conn.fetchval("SELECT 1")
        return value == 1
    finally:
        await conn.close()
