"""Apply the Procrastinate job-queue schema.

Revision ID: 20260928_0001
Revises:
Create Date: 2026-09-28
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from procrastinate.schema import SchemaManager
from sqlalchemy import inspect, text

revision: str = "20260928_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = inspect(bind).get_table_names()
    if "procrastinate_jobs" in tables:
        return
    sql = SchemaManager.get_schema()
    # schema.sql is a full script (functions, tables, triggers).
    bind.exec_driver_sql(sql)


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(text("DROP TABLE IF EXISTS procrastinate_events CASCADE"))
    bind.execute(text("DROP TABLE IF EXISTS procrastinate_jobs CASCADE"))
    bind.execute(text("DROP TABLE IF EXISTS procrastinate_periodic_defers CASCADE"))
