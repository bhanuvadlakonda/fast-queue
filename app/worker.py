"""Procrastinate worker process.

Separate start command from the API. Serves GET /healthz on PORT so Railway
has a liveness probe even though this service has no public domain.
"""

from __future__ import annotations

import asyncio
import logging
import os
from app.jobs import ping
from app.schema import ensure_schema
from app.settings import get_settings
from app.tasks import bind_database, procrastinate_app

log = logging.getLogger(__name__)

_ready = asyncio.Event()
_db_ok = False


def _http_response(status: int, body: bytes) -> bytes:
    reason = {200: "OK", 503: "Service Unavailable"}.get(status, "OK")
    return (
        f"HTTP/1.1 {status} {reason}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii") + body


async def _handle_health(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        await asyncio.wait_for(reader.read(2048), timeout=2)
        path = "/"
        # Best-effort request line parse; anything else still gets a probe reply.
        # The buffer is small on purpose — this is liveness, not a web app.
        if _ready.is_set() and _db_ok:
            status, body = 200, b'{"status":"ok","role":"worker"}'
        elif _ready.is_set():
            status, body = 503, b'{"status":"degraded","role":"worker"}'
        else:
            status, body = 503, b'{"status":"starting","role":"worker"}'
        _ = path
        writer.write(_http_response(status, body))
        await writer.drain()
    except Exception:
        log.debug("health probe handler error", exc_info=True)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def serve_health(host: str, port: int) -> asyncio.AbstractServer:
    server = await asyncio.start_server(_handle_health, host=host, port=port)
    log.info("Worker healthcheck listening on %s:%s", host, port)
    return server


async def _db_watch() -> None:
    global _db_ok
    while True:
        try:
            _db_ok = await ping()
        except Exception:
            _db_ok = False
        await asyncio.sleep(5)


async def run_worker() -> None:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is required for the worker")

    health = await serve_health(settings.host, settings.port)
    try:
        bind_database(procrastinate_app)
        async with procrastinate_app.open_async():
            await ensure_schema(procrastinate_app)
            _ready.set()
            watch = asyncio.create_task(_db_watch())
            log.info(
                "Starting Procrastinate worker name=%s concurrency=%s",
                settings.worker_name,
                settings.worker_concurrency,
            )
            try:
                await procrastinate_app.run_worker_async(
                    name=settings.worker_name,
                    concurrency=settings.worker_concurrency,
                )
            finally:
                watch.cancel()
                try:
                    await watch
                except asyncio.CancelledError:
                    pass
    finally:
        health.close()
        await health.wait_closed()


def main() -> None:
    os.environ.setdefault("PORT", str(get_settings().port))
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
