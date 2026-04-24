"""
PostgreSQL schema manager (get_table_info, sync_schema).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..exceptions import DriverOperationError

logger = logging.getLogger(__name__)


class PostgreSQLSchemaManager:
    """Schema introspection and sync for PostgreSQL."""

    def __init__(self, connection: Any) -> None:
        self.conn = connection

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
            rows = cur.fetchall()
            result: List[Dict[str, Any]] = []
            for row in rows:
                result.append(
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2] == "YES",
                        "default": row[3],
                        "primary_key": False,
                    }
                )
            cur.execute(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = 'public'
                  AND tc.table_name = %s
                """,
                (table_name,),
            )
            pk_cols = {r[0] for r in cur.fetchall()}
            for item in result:
                if item["name"] in pk_cols:
                    item["primary_key"] = True
            return result
        except Exception as e:
            raise DriverOperationError(f"Failed to get table info: {e}") from e
        finally:
            cur.close()

    def sync_schema(
        self,
        schema_definition: Dict[str, Any],
        backup_dir: Optional[str],
        create_table_func: Any,
    ) -> Dict[str, Any]:
        del create_table_func, backup_dir
        from code_analysis.core.database.sqlite_to_postgres import (
            create_postgresql_schema,
        )

        create_postgresql_schema(self.conn, schema_definition)
        names = list(schema_definition.get("tables", {}).keys())
        logger.info(
            "PostgreSQL sync_schema applied (tables=%s); FTS virtual tables skipped on PG",
            len(names),
        )
        return {
            "created_tables": names,
            "modified_tables": [],
            "errors": [],
        }
