"""Apply job tables. Used as the API pre-deploy command and locally.

    python -m app.migrate

Equivalent to ``alembic upgrade head`` plus a safety-net
``ensure_schema`` so a first Railway deploy creates Procrastinate tables
even if Alembic is skipped.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.schema import ensure_schema
from app.settings import get_settings
from app.tasks import bind_database, build_app

log = logging.getLogger(__name__)


def alembic_config() -> Config:
    root = Path(__file__).resolve().parent.parent
    return Config(str(root / "alembic.ini"))


def run_alembic() -> None:
    command.upgrade(alembic_config(), "head")


async def run_schema_fallback() -> str:
    app = bind_database(build_app())
    async with app.open_async():
        return await ensure_schema(app)


def main() -> int:
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not get_settings().database_url:
        log.error("DATABASE_URL is required to migrate")
        return 1
    try:
        run_alembic()
    except Exception:
        log.exception("Alembic upgrade failed; falling back to Procrastinate schema apply")
        asyncio.run(run_schema_fallback())
        return 0
    # Alembic is the happy path; still no-op check via ensure_schema.
    asyncio.run(run_schema_fallback())
    return 0


if __name__ == "__main__":
    sys.exit(main())
