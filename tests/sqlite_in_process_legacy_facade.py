"""
Test-only facade: historical direct-SQL-style ``_execute`` / file APIs on
:class:`~code_analysis.core.database_client.client.DatabaseClient` over
:class:`~code_analysis.core.database_client.in_process_rpc_client.InProcessRpcClient`
and :class:`~code_analysis.core.database_driver_pkg.rpc_handlers.RPCHandlers`
(SQLite driver).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import types
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from code_analysis.core.database import entity_cross_ref as ecr_module
from code_analysis.core.database.files import atomic as atomic_module
from code_analysis.core.database.files import crud as crud_module
from code_analysis.core.database.schema_definition import get_schema_definition
from code_analysis.core.database_client.client import DatabaseClient
from code_analysis.core.database_client.in_process_rpc_client import InProcessRpcClient
from code_analysis.core.database_driver_pkg.driver_factory import create_driver
from code_analysis.core.database_driver_pkg.rpc_handlers import RPCHandlers


class SqliteLegacyRpcFacade:
    """Legacy SQL + :mod:`entity_cross_ref` / :mod:`atomic` surface over RPC client."""

    _driver_type = "sqlite"

    def __init__(self, client: DatabaseClient) -> None:
        self._client = client
        self._last_execute_result: Dict[str, Any] = {}
        self._transaction_active = False
        self._transaction_id: Optional[str] = None

        self.clear_file_data = types.MethodType(crud_module.clear_file_data, self)
        self._clear_file_vectors = types.MethodType(
            crud_module._clear_file_vectors, self
        )
        self.update_file_data_atomic = types.MethodType(
            atomic_module.update_file_data_atomic, self
        )
        self.add_entity_cross_ref = types.MethodType(
            ecr_module.add_entity_cross_ref, self
        )
        self.get_dependencies_by_caller = types.MethodType(
            ecr_module.get_dependencies_by_caller, self
        )
        self.get_dependents_by_callee = types.MethodType(
            ecr_module.get_dependents_by_callee, self
        )
        self.delete_entity_cross_ref_for_file = types.MethodType(
            ecr_module.delete_entity_cross_ref_for_file, self
        )

    def begin_transaction(self) -> str:
        tid = self._client.begin_transaction()
        self._transaction_id = tid or None
        self._transaction_active = bool(tid)
        return str(tid)

    def commit_transaction(self, transaction_id: Optional[str] = None) -> None:
        tid = transaction_id if transaction_id is not None else self._transaction_id
        if tid:
            self._client.commit_transaction(tid)
        self._transaction_id = None
        self._transaction_active = False

    def rollback_transaction(self, transaction_id: Optional[str] = None) -> None:
        tid = transaction_id if transaction_id is not None else self._transaction_id
        if tid:
            self._client.rollback_transaction(tid)
        self._transaction_id = None
        self._transaction_active = False

    def close(self) -> None:
        self._client.disconnect()

    def _in_transaction(self) -> bool:
        return self._transaction_active

    def _driver_transaction_id(self) -> Optional[str]:
        return self._transaction_id if self._transaction_active else None

    def _execute(self, sql: str, params: Optional[tuple] = None) -> None:
        tid = self._driver_transaction_id()
        self._last_execute_result = self._client.execute(
            sql, params, transaction_id=tid
        )

    def _commit(self) -> None:
        return None

    def _fetchone(
        self, sql: str, params: Optional[tuple] = None
    ) -> Optional[Dict[str, Any]]:
        tid = self._driver_transaction_id()
        out = self._client.execute(sql, params, transaction_id=tid)
        rows = out.get("data") or []
        return rows[0] if rows else None

    def _fetchall(
        self, sql: str, params: Optional[tuple] = None
    ) -> List[Dict[str, Any]]:
        tid = self._driver_transaction_id()
        out = self._client.execute(sql, params, transaction_id=tid)
        return list(out.get("data") or [])

    def _lastrowid(self) -> Any:
        return self._last_execute_result.get("lastrowid")

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
        *,
        priority: int = 0,
    ) -> Dict[str, Any]:
        tid = (
            transaction_id
            if transaction_id is not None
            else self._driver_transaction_id()
        )
        raw = self._client.execute(sql, params, transaction_id=tid, priority=priority)
        return cast(Dict[str, Any], raw)

    def execute_batch(
        self,
        operations: List[Tuple[str, Optional[Union[tuple, list]]]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        tid = (
            transaction_id
            if transaction_id is not None
            else self._driver_transaction_id()
        )
        raw = self._client.execute_batch(operations, transaction_id=tid)
        return cast(List[Dict[str, Any]], raw)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._client, item)


def make_sqlite_in_process_legacy_facade(
    root: Path,
) -> Tuple[SqliteLegacyRpcFacade, DatabaseClient]:
    """Create a synced temp DB under ``root``; return ``(facade, client)`` for teardown."""
    db_path = root / "test.db"
    backup_dir = root / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    driver = create_driver(
        "sqlite",
        {"path": str(db_path), "backup_dir": str(backup_dir)},
    )
    handlers = RPCHandlers(driver)
    transport = InProcessRpcClient(handlers)
    client = DatabaseClient(rpc_client=transport)
    client.connect()
    client.sync_schema(get_schema_definition(), backup_dir=str(backup_dir))
    return SqliteLegacyRpcFacade(client), client
