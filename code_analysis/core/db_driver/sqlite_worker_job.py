"""
SQLite database worker job for queuemgr.

This job executes database operations in a separate process,
solving thread/process safety issues with SQLite.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import sqlite3
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

from queuemgr.jobs.base import QueueJobBase

logger = logging.getLogger(__name__)


class SQLiteDatabaseJob(QueueJobBase):
    """
    Job for executing SQLite database operations in a separate process.

    This job receives database operation requests and executes them
    in isolation, ensuring thread/process safety.
    """

    def __init__(self, job_id: str, params: Dict[str, Any]) -> None:
        """
        Initialize SQLite database job.

        Args:
            job_id: Unique job identifier
            params: Job parameters containing:
                - operation: Type of operation (execute, fetchone, fetchall,
                  commit, rollback, lastrowid, get_table_info)
                - db_path: Path to SQLite database file
                - sql: SQL statement (for execute, fetchone, fetchall)
                - params: Query parameters tuple (optional)
                - table_name: Table name (for get_table_info)
        """
        super().__init__(job_id, params)
        self.operation = params.get("operation")
        self.db_path = params.get("db_path")
        self.sql = params.get("sql")
        self.query_params = params.get("params")
        self.table_name = params.get("table_name")

    def execute(self) -> None:
        """
        Execute database operation based on params.

        Raises:
            ValidationError: If required parameters are missing
            RuntimeError: If database operation fails
        """
        # Set environment variable to indicate this is a DB worker process
        # This allows direct SQLite driver to be used in this process
        os.environ["CODE_ANALYSIS_DB_WORKER"] = "1"

        # Validate required parameters
        if not self.operation:
            error_msg = "operation parameter is required"
            logger.error(f"SQLiteDatabaseJob {self.job_id}: {error_msg}")
            self.set_result({"success": False, "result": None, "error": error_msg})
            return

        if not self.db_path:
            error_msg = "db_path parameter is required"
            logger.error(f"SQLiteDatabaseJob {self.job_id}: {error_msg}")
            self.set_result({"success": False, "result": None, "error": error_msg})
            return

        # Validate db_path exists
        db_path_obj = Path(self.db_path)
        if not db_path_obj.exists():
            error_msg = f"Database file does not exist: {self.db_path}"
            logger.error(f"SQLiteDatabaseJob {self.job_id}: {error_msg}")
            self.set_result({"success": False, "result": None, "error": error_msg})
            return

        # Create connection
        try:
            conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            # Use WAL for better concurrency characteristics (single-writer model still applies).
            try:
                conn.execute("PRAGMA journal_mode = WAL")
            except Exception:
                # Best-effort: WAL may be unavailable on some filesystems.
                pass
        except Exception as e:
            error_msg = f"Failed to connect to database: {e}"
            logger.error(f"SQLiteDatabaseJob {self.job_id}: {error_msg}")
            self.set_result({"success": False, "result": None, "error": error_msg})
            return

        try:
            result: Union[Dict[str, Any], List[Dict[str, Any]], None] = None

            if self.operation == "execute":
                if not self.sql:
                    raise ValueError("sql parameter is required for execute operation")
                cursor = conn.cursor()
                if self.query_params:
                    cursor.execute(self.sql, self.query_params)
                else:
                    cursor.execute(self.sql)
                # IMPORTANT:
                # This worker runs each operation in its own short-lived connection.
                # We must commit here, otherwise close() would roll back writes.
                conn.commit()
                result = {
                    "lastrowid": cursor.lastrowid,
                    "rowcount": cursor.rowcount,
                }

            elif self.operation == "fetchone":
                if not self.sql:
                    raise ValueError("sql parameter is required for fetchone operation")
                cursor = conn.cursor()
                if self.query_params:
                    cursor.execute(self.sql, self.query_params)
                else:
                    cursor.execute(self.sql)
                row = cursor.fetchone()
                # Convert Row to dict
                if row:
                    result = dict(zip(row.keys(), row))
                else:
                    result = None

            elif self.operation == "fetchall":
                if not self.sql:
                    raise ValueError("sql parameter is required for fetchall operation")
                cursor = conn.cursor()
                if self.query_params:
                    cursor.execute(self.sql, self.query_params)
                else:
                    cursor.execute(self.sql)
                rows = cursor.fetchall()
                # Convert Rows to list of dicts
                result = [dict(zip(row.keys(), row)) for row in rows]

            elif self.operation == "commit":
                # No-op: execute() auto-commits in this worker model.
                result = None

            elif self.operation == "rollback":
                # No-op: execute() auto-commits in this worker model.
                result = None

            elif self.operation == "lastrowid":
                # Not supported with per-operation connections.
                result = None

            elif self.operation == "get_table_info":
                if not self.table_name:
                    raise ValueError(
                        "table_name parameter is required for get_table_info operation"
                    )
                cursor = conn.cursor()
                cursor.execute(f"PRAGMA table_info({self.table_name})")
                rows = cursor.fetchall()
                # Convert to list of dicts with standard column names
                columns = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
                result = [dict(zip(columns, row)) for row in rows]

            else:
                raise ValueError(f"Unknown operation: {self.operation}")

            # Set success result
            self.set_result({"success": True, "result": result, "error": None})
            logger.debug(
                f"SQLiteDatabaseJob {self.job_id}: "
                f"Operation {self.operation} completed successfully"
            )

        except Exception as e:
            error_msg = f"Database operation failed: {e}"
            # Log with safe truncation of SQL to avoid huge payloads
            sql_truncated = self._truncate_sql(self.sql)
            logger.error(
                f"SQLiteDatabaseJob {self.job_id}: {error_msg}",
                extra={
                    "operation": self.operation,
                    "db_path": self.db_path,
                    "sql": sql_truncated,
                    "has_params": self.query_params is not None,
                },
                exc_info=True,
            )
            # Return structured error
            self.set_result(
                {
                    "success": False,
                    "result": None,
                    "error": {
                        "type": type(e).__name__,
                        "message": str(e),
                        "sql": sql_truncated,
                        "params": (
                            self.query_params
                            if self.query_params and len(str(self.query_params)) < 500
                            else None
                        ),
                    },
                }
            )

        finally:
            # Always close connection
            try:
                conn.close()
            except Exception as e:
                logger.warning(
                    f"SQLiteDatabaseJob {self.job_id}: Error closing connection: {e}"
                )

    def on_start(self) -> None:
        """Called when job starts."""
        logger.info(
            f"SQLiteDatabaseJob {self.job_id}: "
            f"Starting operation {self.operation} on {self.db_path}"
        )

    def on_stop(self) -> None:
        """Called when job is requested to stop."""
        logger.info(
            f"SQLiteDatabaseJob {self.job_id}: Stopping operation {self.operation}"
        )

    def on_end(self) -> None:
        """Called when job ends normally."""
        logger.info(
            f"SQLiteDatabaseJob {self.job_id}: Operation {self.operation} completed"
        )

    def on_error(self, exc: BaseException) -> None:
        """
        Called when job encounters an error.

        Args:
            exc: The exception that occurred
        """
        sql_truncated = self._truncate_sql(self.sql)
        logger.error(
            f"SQLiteDatabaseJob {self.job_id}: Error during operation {self.operation}: {exc}",
            extra={
                "operation": self.operation,
                "db_path": self.db_path,
                "sql": sql_truncated,
            },
            exc_info=True,
        )

    def _truncate_sql(self, sql: Optional[str], max_length: int = 200) -> Optional[str]:
        """
        Truncate SQL statement for logging to avoid huge payloads.

        Args:
            sql: SQL statement to truncate
            max_length: Maximum length before truncation

        Returns:
            Truncated SQL statement or None
        """
        if not sql:
            return None
        if len(sql) <= max_length:
            return sql
        return sql[:max_length] + "..."
