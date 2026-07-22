"""
Module watch_dirs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, List

from code_analysis.core.database.file_edit_lock import editing_lock_holder_is_alive

from ..sql_portable import sql_julian_timestamp_now_expr
from ..worker_db_rpc_priority import BACKGROUND_WORKER_DB_RPC_PRIORITY

# Driver-direct (stage 2): DatabaseClient class removed; ``database`` below is a
# duck-typed driver-shaped object (PostgreSQLDriver in production). Kept as an
# ``Any`` alias so the existing type annotation does not need rewriting.
DatabaseClient = Any

logger = logging.getLogger(__name__)


def _refresh_config(self) -> None:
    """Reload worker watch_dirs from config file if it changed."""
    try:
        if not self.config_path:
            # No on-disk config: cannot discover paths; keep self.watch_dirs unchanged.
            # Clearing to [] made downstream logic treat every DB watch_dir as "not in config"
            # and wipe watch_dir_paths (see file_watcher initialize_watch_dirs).
            return

        if not self.config_path.exists():
            logger.debug("Config path does not exist, skipping refresh")
            return
        mtime = self.config_path.stat().st_mtime
        if self._config_mtime is not None and mtime == self._config_mtime:
            return  # no changes
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_cfg = json.load(f)
        ca_cfg = raw_cfg.get("code_analysis") or raw_cfg
        worker_cfg = ca_cfg.get("worker", {})
        new_watch = worker_cfg.get("watch_dirs", [])
        updated_paths = [Path(p) for p in new_watch if p]

        if set(map(str, updated_paths)) != set(map(str, self.watch_dirs)):
            logger.info(
                "Worker watch_dirs updated from config: "
                f"{[str(p) for p in self.watch_dirs]} -> {[str(p) for p in updated_paths]}"
            )
            self.watch_dirs = updated_paths
        self._config_mtime = mtime
    except Exception as e:
        logger.error(f"Failed to refresh config: {e}", exc_info=True)


async def _enqueue_watch_dirs(self, database: "DatabaseClient") -> int:
    """
    Scan watch_dirs and ensure files are registered for chunking.

    Returns:
        Number of files enqueued (new or marked needing chunking).
    """
    enqueued = 0
    for root in self.watch_dirs:
        try:
            root_path = Path(root)
            if not root_path.exists():
                continue

            for file_path in root_path.rglob("*.py"):
                file_stat = file_path.stat()
                file_mtime = file_stat.st_mtime
                file_path_str = str(file_path)
                # Use execute() for get_file_by_path
                file_result = database.execute(
                    """
                    SELECT id, path, last_modified, editing_pid FROM files
                    WHERE path = ? AND project_id = ?
                    LIMIT 1
                    """,
                    (file_path_str, self.project_id),
                )
                file_rows = (
                    file_result.get("data", []) if isinstance(file_result, dict) else []
                )
                file_rec = file_rows[0] if file_rows else None
                if not file_rec:
                    # Register file and mark as needing chunking
                    file_lines = len(file_path.read_text(encoding="utf-8").splitlines())
                    now_sql = sql_julian_timestamp_now_expr(database)
                    new_id = str(uuid.uuid4())
                    database.execute(
                        f"""
                        INSERT INTO files (id, project_id, path, lines, last_modified, has_docstring, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, {now_sql})
                        """,
                        (
                            new_id,
                            self.project_id,
                            file_path_str,
                            file_lines,
                            file_mtime,
                            False,
                        ),
                    )
                    # Use execute() for mark_file_needs_chunking
                    database.execute(
                        """
                        UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?
                        """,
                        (file_path_str, self.project_id),
                    )
                    enqueued += 1
                else:
                    if editing_lock_holder_is_alive(file_rec.get("editing_pid")):
                        continue
                    db_mtime = file_rec.get("last_modified")
                    if db_mtime is None or db_mtime != file_mtime:
                        database.execute(
                            """
                            UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?
                            """,
                            (file_path_str, self.project_id),
                        )
                        enqueued += 1
        except Exception as e:
            logger.error(f"Error scanning watch_dir {root}: {e}", exc_info=True)
    return enqueued
