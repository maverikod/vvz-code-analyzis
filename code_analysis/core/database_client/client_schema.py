"""
Schema operations methods for client.

Provides methods for table and schema management.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class _ClientSchemaMixin:
    """Mixin class with schema operation methods."""

    def create_table(self, schema: Dict[str, Any]) -> bool:
        """Create table.

        Args:
            schema: Table schema definition

        Returns:
            True if table was created successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call("create_table", {"schema": schema})
        return self._extract_success(response)

    def drop_table(self, table_name: str) -> bool:
        """Drop table.

        Args:
            table_name: Name of table to drop

        Returns:
            True if table was dropped successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call("drop_table", {"table_name": table_name})
        return self._extract_success(response)

    def alter_table(self, table_name: str, changes: Dict[str, Any]) -> bool:
        """Alter table.

        Args:
            table_name: Name of table to alter
            changes: Dictionary with table changes

        Returns:
            True if table was altered successfully

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call(
            "alter_table", {"table_name": table_name, "changes": changes}
        )
        return self._extract_success(response)

    def get_table_info(self, table_name: str) -> List[Dict[str, Any]]:
        """Get table information.

        Args:
            table_name: Name of table

        Returns:
            List of column information dictionaries

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call("get_table_info", {"table_name": table_name})
        result_data = self._extract_result_data(response)
        # result_data is already the list from DataResult, not a dict
        if isinstance(result_data, list):
            return result_data
        # Fallback: if it's a dict, try to get "data" key
        if isinstance(result_data, dict):
            return result_data.get("data", [])
        return []

    def get_schema_version(self) -> str:
        """Get database schema version.

        Returns:
            Schema version string

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        response = self.rpc_client.call("get_schema_version", {})
        result_data = self._extract_result_data(response)
        return result_data.get("version", "")

    def sync_schema(
        self,
        schema_definition: Dict[str, Any],
        backup_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync database schema.

        Args:
            schema_definition: Schema definition dictionary
            backup_dir: Optional backup directory

        Returns:
            Sync results dictionary

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        params: Dict[str, Any] = {"schema_definition": schema_definition}
        if backup_dir:
            params["backup_dir"] = backup_dir
        response = self.rpc_client.call("sync_schema", params)
        return self._extract_result_data(response)
