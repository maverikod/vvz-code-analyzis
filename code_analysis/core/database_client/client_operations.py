"""
Database operations methods for client.

Provides CRUD operations (insert, update, delete, select, execute).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from ..database_driver_pkg.request import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
)


class _ClientOperationsMixin:
    """Mixin class with database operation methods."""

    def insert(self, table_name: str, data: Dict[str, Any]) -> int:
        """Insert row into table.

        Args:
            table_name: Name of table
            data: Row data as dictionary

        Returns:
            Row ID of inserted row

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        request = InsertRequest(table_name=table_name, data=data)
        response = self.rpc_client.call("insert", request.to_dict())
        result_data = self._extract_result_data(response)
        data_inner = (
            result_data.get("data", result_data)
            if isinstance(result_data, dict)
            else {}
        )
        return data_inner.get("row_id", 0) if isinstance(data_inner, dict) else 0

    def update(
        self,
        table_name: str,
        where: Dict[str, Any],
        data: Dict[str, Any],
    ) -> int:
        """Update rows in table.

        Args:
            table_name: Name of table
            where: WHERE clause conditions
            data: Data to update

        Returns:
            Number of affected rows

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        request = UpdateRequest(table_name=table_name, where=where, data=data)
        response = self.rpc_client.call("update", request.to_dict())
        result_data = self._extract_result_data(response)
        data_inner = (
            result_data.get("data", result_data)
            if isinstance(result_data, dict)
            else {}
        )
        return data_inner.get("affected_rows", 0) if isinstance(data_inner, dict) else 0

    def delete(self, table_name: str, where: Dict[str, Any]) -> int:
        """Delete rows from table.

        Args:
            table_name: Name of table
            where: WHERE clause conditions

        Returns:
            Number of affected rows

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        request = DeleteRequest(table_name=table_name, where=where)
        response = self.rpc_client.call("delete", request.to_dict())
        result_data = self._extract_result_data(response)
        data_inner = (
            result_data.get("data", result_data)
            if isinstance(result_data, dict)
            else {}
        )
        return data_inner.get("affected_rows", 0) if isinstance(data_inner, dict) else 0

    def select(
        self,
        table_name: str,
        where: Optional[Dict[str, Any]] = None,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Select rows from table.

        Args:
            table_name: Name of table
            where: WHERE clause conditions (optional)
            columns: List of columns to select (optional, None = all)
            limit: Maximum number of rows to return (optional)
            offset: Number of rows to skip (optional)
            order_by: List of columns for ORDER BY (optional)

        Returns:
            List of rows as dictionaries

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        request = SelectRequest(
            table_name=table_name,
            where=where,
            columns=columns,
            limit=limit,
            offset=offset,
            order_by=order_by,
        )
        response = self.rpc_client.call("select", request.to_dict())
        result_data = self._extract_result_data(response)
        # For DataResult, _extract_result_data returns {"success": True, "data": [...]}
        # We need to extract the list from "data" key
        if isinstance(result_data, list):
            return result_data
        # If it's a dict (DataResult format), extract "data" key
        if isinstance(result_data, dict):
            data = result_data.get("data")
            if isinstance(data, list):
                return data
        # Fallback: return empty list
        return []

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute raw SQL query.

        Args:
            sql: SQL query string
            params: Optional parameters for query

        Returns:
            Query result as dictionary. For SELECT queries, contains "data" key with list of rows.
            For other queries, contains "affected_rows" and "lastrowid" keys.

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rpc_params = {"sql": sql, "params": params}
        if transaction_id is not None:
            rpc_params["transaction_id"] = transaction_id
        response = self.rpc_client.call("execute", rpc_params)
        result = self._extract_result_data(response)
        # _extract_result_data() returns the full result dict from RPC
        # For SuccessResult: {"success": True, "data": {"affected_rows": ..., "lastrowid": ..., "data": [...]}}
        # The "data" key contains the actual driver result
        if isinstance(result, dict):
            # Extract the actual driver result from "data" key
            driver_result = result.get("data", {})
            # driver_result should be the full result from driver.execute()
            # For SELECT: {"affected_rows": ..., "lastrowid": ..., "data": [...]}
            # For other: {"affected_rows": ..., "lastrowid": ...}
            if isinstance(driver_result, dict):
                return driver_result
            # Fallback: if not a dict, return empty dict
            return {}
        # Fallback: if result is not a dict, return empty dict
        return {}

    def execute_batch(
        self,
        operations: List[Tuple[str, Optional[Union[tuple, list]]]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute multiple SQL statements in one RPC round-trip.

        Args:
            operations: List of (sql, params) where params is optional tuple or list
            transaction_id: Optional transaction ID for all operations

        Returns:
            List of result dicts (same shape as execute(): data, affected_rows, lastrowid)

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rpc_ops = []
        for sql, params in operations:
            rpc_ops.append(
                {
                    "sql": sql,
                    "params": list(params) if params is not None else None,
                }
            )
        rpc_params: Dict[str, Any] = {"operations": rpc_ops}
        if transaction_id is not None:
            rpc_params["transaction_id"] = transaction_id
        response = self.rpc_client.call("execute_batch", rpc_params)
        result = self._extract_result_data(response)
        if isinstance(result, dict):
            # SuccessResult: {"success": True, "data": {"results": [...]}}
            inner = result.get("data", result)
            if isinstance(inner, dict):
                results = inner.get("results", [])
                if isinstance(results, list):
                    return results
        return []

    def add_code_chunk(
        self,
        file_id: int,
        project_id: str,
        chunk_uuid: str,
        chunk_type: str,
        chunk_text: str,
        chunk_ordinal: Optional[int] = None,
        vector_id: Optional[int] = None,
        embedding_model: Optional[str] = None,
        bm25_score: Optional[float] = None,
        embedding_vector: Optional[str] = None,
        token_count: Optional[int] = None,
        class_id: Optional[int] = None,
        function_id: Optional[int] = None,
        method_id: Optional[int] = None,
        line: Optional[int] = None,
        ast_node_type: Optional[str] = None,
        source_type: Optional[str] = None,
        binding_level: int = 0,
    ) -> int:
        """Add or replace code chunk row. Uses INSERT OR REPLACE by chunk_uuid.

        Persists chunk text, embedding vector (and model), and token count.

        Args:
            file_id: File ID
            project_id: Project UUID
            chunk_uuid: Unique chunk identifier (UUID5)
            chunk_type: Type of chunk (e.g. DocBlock)
            chunk_text: Text content of the chunk
            chunk_ordinal: Ordinal position
            vector_id: FAISS index ID (optional)
            embedding_model: Model name (optional)
            bm25_score: BM25 score (optional)
            embedding_vector: JSON string of embedding vector (optional)
            token_count: Number of tokens in chunk (optional)
            class_id, function_id, method_id: AST bindings (optional)
            line: Line number (optional)
            ast_node_type: AST node type (optional)
            source_type: Source type (optional)
            binding_level: Nesting level (default 0)

        Returns:
            Chunk ID (lastrowid)
        """
        if embedding_vector is not None and not (
            embedding_model and str(embedding_model).strip()
        ):
            raise ValueError(
                "embedding_model is required when embedding_vector is set; "
                "a vector without model cannot be used for search"
            )
        sql = """
            INSERT OR REPLACE INTO code_chunks
            (
                file_id, project_id, chunk_uuid, chunk_type, chunk_text,
                chunk_ordinal, vector_id, embedding_model, bm25_score,
                embedding_vector, token_count, class_id, function_id, method_id,
                line, ast_node_type, source_type, binding_level,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, julianday('now'))
        """
        params = (
            file_id,
            project_id,
            chunk_uuid,
            chunk_type,
            chunk_text,
            chunk_ordinal,
            vector_id,
            embedding_model,
            bm25_score,
            embedding_vector,
            token_count,
            class_id,
            function_id,
            method_id,
            line,
            ast_node_type,
            source_type,
            binding_level,
        )
        result = self.execute(sql, params)
        return result.get("lastrowid") or 0
