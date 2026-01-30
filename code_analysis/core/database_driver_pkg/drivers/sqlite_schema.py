"""
SQLite schema management for SQLite driver.

Handles schema operations (sync_schema, get_table_info).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..exceptions import DriverOperationError


class SQLiteSchemaManager:
    """Manages SQLite schema operations."""

    def __init__(self, connection):
        """Initialize schema manager.

        Args:
            connection: SQLite connection object
        """
        self.conn = connection

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get information about table columns.

        Args:
            table_name: Name of the table

        Returns:
            List of dictionaries with column information (name, type, nullable, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        try:
            cursor = self.conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            rows = cursor.fetchall()
            result = []
            for row in rows:
                result.append(
                    {
                        "name": row[1],
                        "type": row[2],
                        "nullable": not row[3],
                        "default": row[4],
                        "primary_key": bool(row[5]),
                    }
                )
            return result
        except Exception as e:
            raise DriverOperationError(f"Failed to get table info: {e}") from e

    def sync_schema(
        self,
        schema_definition: Dict[str, Any],
        backup_dir: Optional[str],
        create_table_func,
    ) -> Dict[str, Any]:
        """Synchronize database schema.

        Args:
            schema_definition: Complete schema definition (tables, columns, constraints)
            backup_dir: Optional directory for backups before schema changes
            create_table_func: Function to create table (from driver)

        Returns:
            Dictionary with sync results (created_tables, modified_tables, etc.)

        Raises:
            DriverOperationError: If operation fails
        """
        if not self.conn:
            raise DriverOperationError("Database connection not established")

        # This is a simplified implementation
        # Full implementation would compare existing schema with new schema
        # and apply changes incrementally
        try:
            result: Dict[str, Any] = {
                "created_tables": [],
                "modified_tables": [],
                "errors": [],
            }

            tables = schema_definition.get("tables", [])
            for table_schema in tables:
                try:
                    table_name = table_schema.get("name")
                    if not table_name:
                        continue

                    # Check if table exists
                    cursor = self.conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (table_name,),
                    )
                    exists = cursor.fetchone() is not None

                    if not exists:
                        create_table_func(table_schema)
                        result["created_tables"].append(table_name)
                    else:
                        # Table exists - could implement ALTER TABLE logic here
                        result["modified_tables"].append(table_name)
                except Exception as e:
                    result["errors"].append(f"Error processing table {table_name}: {e}")

            if result["errors"]:
                self.conn.rollback()
                raise DriverOperationError(
                    "Schema sync had errors: " + "; ".join(result["errors"])
                ) from None

            # Create virtual tables (e.g. FTS5 code_content_fts) if missing
            virtual_tables = schema_definition.get("virtual_tables", [])
            for vt_def in virtual_tables:
                vt_name = vt_def.get("name")
                if not vt_name:
                    continue
                try:
                    cursor = self.conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                        (vt_name,),
                    )
                    exists = cursor.fetchone() is not None
                    if not exists:
                        vt_type = vt_def.get("type", "fts5")
                        columns = vt_def.get("columns", [])
                        options = vt_def.get("options", {})
                        cols_str = ", ".join(columns)
                        opts_parts = [f"{k}='{v}'" for k, v in options.items()]
                        opts_str = ", " + ", ".join(opts_parts) if opts_parts else ""
                        create_sql = (
                            f"CREATE VIRTUAL TABLE IF NOT EXISTS {vt_name} "
                            f"USING {vt_type}({cols_str}{opts_str})"
                        )
                        cursor.execute(create_sql)
                        result["created_tables"].append(vt_name)
                except Exception as e:
                    result["errors"].append(
                        f"Error creating virtual table {vt_name}: {e}"
                    )

            if result["errors"]:
                self.conn.rollback()
                raise DriverOperationError(
                    "Schema sync had errors: " + "; ".join(result["errors"])
                ) from None

            self.conn.commit()
            return result
        except Exception as e:
            self.conn.rollback()
            raise DriverOperationError(f"Failed to sync schema: {e}") from e
