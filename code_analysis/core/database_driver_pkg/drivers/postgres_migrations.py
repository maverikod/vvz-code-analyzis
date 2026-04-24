"""
Connection-time schema ensure for PostgreSQL (idempotent CREATE TABLE / INDEX).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from code_analysis.core.database.sqlite_to_postgres import create_postgresql_schema

logger = logging.getLogger(__name__)


def _ensure_missing_column(
    conn: Any,
    *,
    table_name: str,
    column_name: str,
    add_sql: str,
) -> None:
    """ALTER TABLE ADD COLUMN when missing (CREATE TABLE IF NOT EXISTS does not upgrade)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            (table_name, column_name),
        )
        if cur.fetchone() is not None:
            return
        logger.info("PostgreSQL migrate: adding column %s.%s", table_name, column_name)
        cur.execute(add_sql)
    conn.commit()


def ensure_postgres_schema(conn: Any, schema_definition: Dict[str, Any]) -> None:
    """Create tables and indexes if missing (FTS5 virtual tables are not created)."""
    create_postgresql_schema(conn, schema_definition)
    _ensure_missing_column(
        conn,
        table_name="code_chunks",
        column_name="vectorization_skipped",
        add_sql=(
            "ALTER TABLE code_chunks ADD COLUMN vectorization_skipped "
            "INTEGER DEFAULT 0"
        ),
    )
