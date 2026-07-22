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

from typing import Any, Dict, List, Optional, Protocol, Tuple, cast

# NOTE: CodeDatabase (the class this facade used to be typed against) was
# deleted as dead code (stage 2 dead-code cleanup, sub-step A1) - it had zero
# production instantiations. This facade, and the ``db`` param it wraps, are
# now reachable only via that already-dead CodeDatabase-monkeypatch chain
# (see core/database/files/trash.py); kept per task scope (KEEP the ~30
# underlying core/database/*.py modules) and duck-typed as ``Any`` below.


class TrashSqlDriver(Protocol):
    """Minimal surface used by ``*_via_driver`` and ``trash_standalone_support``.

    Modeled on :class:`~code_analysis.core.database_driver_pkg.drivers.postgres.PostgreSQLDriver`
    (the post-flip caller, stage 2). Pre-flip, production call sites
    (``code_analysis/commands/file_management/*.py``) still pass the existing
    :class:`~code_analysis.core.database_client.client.DatabaseClient`, which satisfies
    this protocol structurally at runtime (duck-typed ``execute``/``execute_batch``) but
    not nominally for mypy - ``DatabaseClient.execute_batch`` is a strict superset (extra
    ``priority`` keyword-only param, wider per-operation param type accepting ``list`` as
    well as ``tuple``). Those call sites use ``cast(Any, database)`` to bridge this
    transitional mismatch; the cast becomes a no-op once construction hands out a real
    ``PostgreSQLDriver`` there instead.
    """

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

    def __init__(self, db: Any) -> None:
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


def trash_driver_for_codedatabase(db: Any) -> TrashCodeDatabaseDriverFacade:
    """Return trash driver for codedatabase."""
    return TrashCodeDatabaseDriverFacade(db)
