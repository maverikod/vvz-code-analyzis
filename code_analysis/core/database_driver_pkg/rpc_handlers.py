"""
RPC method handlers for database driver operations.

Handles individual RPC method calls by delegating to driver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from .drivers.base import BaseDatabaseDriver


class RPCHandlers:
    """RPC method handlers for database operations."""

    def __init__(self, driver: BaseDatabaseDriver):
        """Initialize RPC handlers.

        Args:
            driver: Database driver instance
        """
        self.driver = driver

    def handle_create_table(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create_table RPC method."""
        schema = params.get("schema")
        if not schema:
            raise ValueError("schema parameter is required")
        success = self.driver.create_table(schema)
        return {"success": success}

    def handle_drop_table(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle drop_table RPC method."""
        table_name = params.get("table_name")
        if not table_name:
            raise ValueError("table_name parameter is required")
        success = self.driver.drop_table(table_name)
        return {"success": success}

    def handle_insert(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle insert RPC method."""
        table_name = params.get("table_name")
        data = params.get("data")
        if not table_name or not data:
            raise ValueError("table_name and data parameters are required")
        row_id = self.driver.insert(table_name, data)
        return {"row_id": row_id}

    def handle_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle update RPC method."""
        table_name = params.get("table_name")
        where = params.get("where")
        data = params.get("data")
        if not table_name or not where or not data:
            raise ValueError("table_name, where, and data parameters are required")
        affected_rows = self.driver.update(table_name, where, data)
        return {"affected_rows": affected_rows}

    def handle_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle delete RPC method."""
        table_name = params.get("table_name")
        where = params.get("where")
        if not table_name or not where:
            raise ValueError("table_name and where parameters are required")
        affected_rows = self.driver.delete(table_name, where)
        return {"affected_rows": affected_rows}

    def handle_select(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle select RPC method."""
        table_name = params.get("table_name")
        if not table_name:
            raise ValueError("table_name parameter is required")
        where = params.get("where")
        columns = params.get("columns")
        limit = params.get("limit")
        offset = params.get("offset")
        order_by = params.get("order_by")
        rows = self.driver.select(table_name, where, columns, limit, offset, order_by)
        return {"data": rows}

    def handle_execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle execute RPC method."""
        sql = params.get("sql")
        if not sql:
            raise ValueError("sql parameter is required")
        params_tuple = params.get("params")
        result = self.driver.execute(sql, params_tuple)
        return result

    def handle_begin_transaction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle begin_transaction RPC method."""
        transaction_id = self.driver.begin_transaction()
        return {"transaction_id": transaction_id}

    def handle_commit_transaction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle commit_transaction RPC method."""
        transaction_id = params.get("transaction_id")
        if not transaction_id:
            raise ValueError("transaction_id parameter is required")
        success = self.driver.commit_transaction(transaction_id)
        return {"success": success}

    def handle_rollback_transaction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle rollback_transaction RPC method."""
        transaction_id = params.get("transaction_id")
        if not transaction_id:
            raise ValueError("transaction_id parameter is required")
        success = self.driver.rollback_transaction(transaction_id)
        return {"success": success}

    def handle_get_table_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get_table_info RPC method."""
        table_name = params.get("table_name")
        if not table_name:
            raise ValueError("table_name parameter is required")
        info = self.driver.get_table_info(table_name)
        return {"info": info}

    def handle_sync_schema(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle sync_schema RPC method."""
        schema_definition = params.get("schema_definition")
        if not schema_definition:
            raise ValueError("schema_definition parameter is required")
        backup_dir = params.get("backup_dir")
        result = self.driver.sync_schema(schema_definition, backup_dir)
        return result
