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

            self.conn.commit()
            return result
        except Exception as e:
            self.conn.rollback()
            raise DriverOperationError(f"Failed to sync schema: {e}") from e
