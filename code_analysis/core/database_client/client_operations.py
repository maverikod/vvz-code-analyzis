"""
Database operations methods for client.

Provides CRUD operations (insert, update, delete, select, execute).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union, cast

from code_analysis.core.database_driver_pkg.drivers.base import DbIdentity

from code_analysis.core.database.code_chunk_sql import (
    CODE_CHUNK_UPSERT_PARAM_COUNT,
    CODE_CHUNK_UPSERT_SQL,
    build_code_chunk_upsert_batch,
)
from code_analysis.core.database.logical_write_program import LogicalWriteProgramV1

from .client_base import _DatabaseClientBase
from .protocol import (
    DeleteRequest,
    InsertRequest,
    SelectRequest,
    UpdateRequest,
)

logger = logging.getLogger(__name__)

_LOGICAL_WRITE_LOCK_SCOPES: Set[str] = {
    "none",
    "project_write",
    "project_read",
}


class _ClientOperationsMixin(_DatabaseClientBase):
    """Mixin class with database operation methods."""

    def insert(self, table_name: str, data: Dict[str, Any]) -> Optional[DbIdentity]:
        """Insert row into table.

        Args:
            table_name: Name of table
            data: Row data as dictionary

        Returns:
            Primary key / row identity from the driver (integer or UUID string), or
            ``None`` when the driver does not report an identity.

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
        if not isinstance(data_inner, dict) or "row_id" not in data_inner:
            return None
        row_id = data_inner.get("row_id")
        if row_id is None:
            return None
        if isinstance(row_id, (int, str)):
            return row_id
        return None

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
        *,
        priority: int = 0,
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
        response = self.rpc_client.call("select", request.to_dict(), priority=priority)
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
        *,
        priority: int = 0,
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
        sql_preview = (sql.strip()[:80] + "…") if len(sql.strip()) > 80 else sql.strip()
        logger.debug(
            "[CHAIN] client execute method=execute sql_preview=%s tid=%s",
            sql_preview,
            (transaction_id[:8] + "…") if transaction_id else None,
        )
        response = self.rpc_client.call("execute", rpc_params, priority=priority)
        result = self._extract_result_data(response)
        # _extract_result_data() returns the full result dict from RPC
        # For SuccessResult: {"success": True, "data": {"affected_rows": ..., "lastrowid": ..., "data": [...]}}
        # The "data" key contains the actual driver result
        if isinstance(result, dict):
            # Extract the actual driver result from "data" key
            driver_result = result.get("data", {})
            # driver_result: SELECT has "data" list; other ops have affected_rows, lastrowid
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
        *,
        priority: int = 0,
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
        logger.debug(
            "[CHAIN] client execute_batch n_ops=%s tid=%s",
            len(operations),
            (transaction_id[:8] + "…") if transaction_id else None,
        )
        response = self.rpc_client.call("execute_batch", rpc_params, priority=priority)
        result = self._extract_result_data(response)
        if isinstance(result, dict):
            # SuccessResult: {"success": True, "data": {"results": [...]}}
            inner = result.get("data", result)
            if isinstance(inner, dict):
                results = inner.get("results", [])
                if isinstance(results, list):
                    return results
        return []

    def execute_logical_write_operation(
        self, program: LogicalWriteProgramV1
    ) -> dict[str, Any]:
        """Run one logical write program in a single RPC (full server-side transaction)."""
        batches = program.get("batches")
        if batches is None or not isinstance(batches, list) or len(batches) == 0:
            raise ValueError(
                "LogicalWriteProgramV1 requires non-empty batches",
            )
        rpc_batches: list[list[dict[str, Any]]] = []
        for inner in batches:
            inner_ops: list[dict[str, Any]] = []
            for sql, params in inner:
                inner_ops.append(
                    {
                        "sql": sql,
                        "params": list(params) if params is not None else None,
                    }
                )
            rpc_batches.append(inner_ops)
        rpc_params: Dict[str, Any] = {"batches": rpc_batches}
        if program.get("defer_constraints") is True:
            rpc_params["defer_constraints"] = True
        if "operation_name" in program:
            opn = program["operation_name"]
            if not isinstance(opn, str):
                raise ValueError("operation_name must be a string when set")
            rpc_params["operation_name"] = opn
        if "project_id" in program:
            pid = program["project_id"]
            if not isinstance(pid, str):
                raise ValueError("project_id must be a string when set")
            rpc_params["project_id"] = pid
        if "lock_scope" in program:
            lscope = program["lock_scope"]
            if lscope not in _LOGICAL_WRITE_LOCK_SCOPES:
                raise ValueError(
                    "lock_scope must be one of: none, project_write, project_read",
                )
            rpc_params["lock_scope"] = lscope
        logger.debug(
            "[CHAIN] client execute_logical_write_operation n_batches=%s operation_name=%s project_id=%s",
            len(rpc_batches),
            program.get("operation_name"),
            program.get("project_id"),
        )
        response = self.rpc_client.call("execute_logical_write_operation", rpc_params)
        return cast(dict[str, Any], self._extract_result_data(response))

    def purge_file_ids_cascade(
        self,
        project_id: str,
        file_ids: Sequence[str],
        *,
        operation_name: str = "file_cascade_purge",
    ) -> None:
        """Hard-delete file rows and all dependent index data (RPC → driver → DB)."""
        from code_analysis.core.database.file_purge_cascade import (
            purge_file_ids_cascade_via_client,
        )

        purge_file_ids_cascade_via_client(
            self,
            project_id,
            file_ids,
            operation_name=operation_name,
        )

    def clear_file_data(self, file_id: str) -> None:
        """Drop all rows tied to ``file_id`` (chunks, vectors, entities, trees).

        Same semantics as :meth:`code_analysis.core.database.files.crud.clear_file_data`
        on :class:`~code_analysis.core.database.base.CodeDatabase`, implemented via
        :func:`~code_analysis.core.database.files.trash_standalone_support.clear_file_data_via_driver`
        so SQLite and PostgreSQL stay aligned (no legacy ``chunk_embeddings`` DML).

        Uses background RPC priority for worker-style callers (e.g. file watcher
        absolute-path dedup).
        """
        from code_analysis.core.database.files import trash_standalone_support as _tss
        from code_analysis.core.worker_db_rpc_priority import (
            BACKGROUND_WORKER_DB_RPC_PRIORITY,
        )

        class _ClientTrashAdapter:
            __slots__ = ("_client", "_priority")

            def __init__(self, client: Any, priority: int) -> None:
                self._client = client
                self._priority = priority

            def execute(
                self,
                sql: str,
                params: Optional[tuple] = None,
                transaction_id: Optional[str] = None,
            ) -> Any:
                return self._client.execute(
                    sql,
                    params,
                    transaction_id=transaction_id,
                    priority=self._priority,
                )

            def execute_batch(
                self,
                operations: List[Tuple[str, Optional[Union[tuple, list]]]],
                transaction_id: Optional[str] = None,
            ) -> List[Dict[str, Any]]:
                return self._client.execute_batch(
                    operations,
                    transaction_id=transaction_id,
                    priority=self._priority,
                )

        _tss.clear_file_data_via_driver(
            _ClientTrashAdapter(self, BACKGROUND_WORKER_DB_RPC_PRIORITY),
            str(file_id),
        )

    def qa_set_db_retry_injections(self, remaining: int = 1) -> Dict[str, Any]:
        """QA only: arm driver to raise synthetic transients on next N self-managed writes.

        Requires ``CODE_ANALYSIS_ENABLE_QA_MCP_HOOKS=1`` in the database driver process.
        """
        response = self.rpc_client.call(
            "qa_set_db_retry_injections",
            {"remaining": int(remaining)},
        )
        result = self._extract_result_data(response)
        if isinstance(result, dict):
            inner = result.get("data")
            if isinstance(inner, dict):
                return inner
            return result
        return {}

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
        sql = CODE_CHUNK_UPSERT_SQL.strip()
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
        if len(params) != CODE_CHUNK_UPSERT_PARAM_COUNT:
            raise ValueError(
                f"code_chunk upsert: internal param tuple length {len(params)} "
                f"!= {CODE_CHUNK_UPSERT_PARAM_COUNT}"
            )
        result = self.execute(sql, params)
        return result.get("lastrowid") or 0

    def upsert_code_chunk(
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
        """Portable alias for :meth:`add_code_chunk` (upsert by ``chunk_uuid``)."""
        return self.add_code_chunk(
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

    def upsert_code_chunks_batch(
        self,
        param_rows: Sequence[Tuple[Any, ...]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Batch upsert ``code_chunks`` rows using portable SQL (driver adapts per dialect).

        Each row is the same :data:`~code_analysis.core.database.code_chunk_sql.CODE_CHUNK_UPSERT_PARAM_COUNT`-value
        tuple as :meth:`add_code_chunk`, in
        :data:`~code_analysis.core.database.code_chunk_sql.CODE_CHUNK_UPSERT_PARAM_ORDER`.
        """
        return self.execute_batch(
            build_code_chunk_upsert_batch(param_rows),
            transaction_id=transaction_id,
        )
