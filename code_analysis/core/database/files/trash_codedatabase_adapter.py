"""
Adapter from :class:`~code_analysis.core.database.base.CodeDatabase` to the driver
API expected by :mod:`~code_analysis.core.database.files.trash_standalone_support`.

``driver_fetchone`` / ``driver_fetchall`` call ``driver.execute(sql, params, None)``
and require SELECT results as ``{"data": rows}``. The in-process legacy SQLite stack
often returns ``None`` from ``execute`` and exposes ``fetchone`` / ``fetchall``
instead; :class:`CodeDatabase` already normalizes both in ``_fetchall`` and
``_execute``. This facade implements the RPC-shaped ``execute`` + ``execute_batch``
surface by delegating to those methods so production trash ops share a single
implementation with the driver process (``*_via_driver``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from code_analysis.core.database.base import CodeDatabase


class TrashSqlDriver(Protocol):
    """Minimal surface used by ``*_via_driver`` and ``trash_standalone_support``."""

    def execute(
        self,
        sql: str,
        params: Optional[tuple] = None,
        transaction_id: Optional[str] = None,
    ) -> Any:
        """Execute SQL and return an RPC-shaped payload."""
        ...

    def execute_batch(
        self,
        operations: List[Tuple[str, Optional[tuple]]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a batch of SQL operations."""
        ...


class TrashCodeDatabaseDriverFacade:
    """Delegates to :class:`CodeDatabase` with the ``execute`` result shape RPC helpers use."""

    __slots__ = ("_db", "_trash_facade_underlying_driver")

    def __init__(self, db: CodeDatabase) -> None:
        """Initialize the instance."""
        self._db = db
        self._trash_facade_underlying_driver = db.driver

    def execute(
        self,
        sql: str,
        params: Optional[Tuple[Any, ...]] = None,
        transaction_id: Optional[str] = None,
    ) -> Any:
        """Execute the command."""
        del transaction_id  # active tx via :meth:`CodeDatabase._driver_transaction_id`
        if sql.strip().upper().startswith("SELECT"):
            rows = self._db._fetchall(sql, params)
            return {"data": rows}
        self._db._execute(sql, params)
        last = getattr(self._db, "_last_execute_result", None)
        if isinstance(last, dict):
            return last
        return {"data": []}

    def execute_batch(
        self,
        operations: List[Tuple[str, Optional[tuple]]],
        transaction_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return execute batch."""
        return cast(
            List[Dict[str, Any]],
            self._db.execute_batch(operations, transaction_id),
        )


def trash_driver_for_codedatabase(db: CodeDatabase) -> TrashCodeDatabaseDriverFacade:
    """Return trash driver for codedatabase."""
    return TrashCodeDatabaseDriverFacade(db)
