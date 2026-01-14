"""
Module watch_dirs.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..database_client.client import DatabaseClient

logger = logging.getLogger(__name__)


def _refresh_config(self) -> None:
    """Reload worker watch_dirs from config file if it changed."""
    try:
        # load dynamic watch list
        dynamic_paths: List[Path] = []
        if self.dynamic_watch_file and self.dynamic_watch_file.exists():
            try:
                with open(self.dynamic_watch_file, "r", encoding="utf-8") as df:
                    dyn = json.load(df)
                    for p in dyn.get("watch_dirs", []):
                        if p:
                            path_obj = Path(p)
                            setattr(path_obj, "is_dynamic", True)
                            dynamic_paths.append(path_obj)
            except Exception as e:
                logger.error(f"Failed to load dynamic watch dirs: {e}", exc_info=True)

        if not self.config_path:
            # Only dynamic paths
            combined = dynamic_paths
            if set(map(str, combined)) != set(map(str, self.watch_dirs)):
                self.watch_dirs = combined
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
        new_watch_paths = [Path(p) for p in new_watch if p]

        # Updated list: new config paths (non-dynamic) + existing dynamic
        updated_paths: List[Path] = []
        for p in new_watch_paths:
            updated_paths.append(p)
        # keep dynamic from file
        updated_paths.extend(dynamic_paths)

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

    Implements dataset-scoped file processing (Step 2 of refactor plan).
    Resolves dataset_id from each watch_dir root.

    Returns:
        Number of files enqueued (new or marked needing chunking).
    """
    from ..project_resolution import normalize_root_dir

    enqueued = 0
    for root in self.watch_dirs:
        try:
            root_path = Path(root)
            if not root_path.exists():
                continue

            # Resolve dataset_id for this watch_dir
            normalized_root = str(normalize_root_dir(root_path))
            dataset_id = getattr(self, "dataset_id", None)
            if not dataset_id:
                # Use execute() for get_dataset_id
                dataset_result = database.execute(
                    """
                    SELECT id FROM datasets
                    WHERE project_id = ? AND root_path = ?
                    LIMIT 1
                    """,
                    (self.project_id, normalized_root),
                )
                dataset_rows = (
                    dataset_result.get("data", [])
                    if isinstance(dataset_result, dict)
                    else []
                )
                if dataset_rows:
                    dataset_id = dataset_rows[0].get("id")
                if not dataset_id:
                    # Create dataset if it doesn't exist
                    import uuid

                    dataset_id = str(uuid.uuid4())
                    database.execute(
                        """
                        INSERT INTO datasets (id, project_id, root_path, created_at)
                        VALUES (?, ?, ?, julianday('now'))
                        """,
                        (dataset_id, self.project_id, normalized_root),
                    )
                    logger.info(
                        f"Created dataset {dataset_id} for watch_dir {normalized_root}"
                    )

            for file_path in root_path.rglob("*.py"):
                file_stat = file_path.stat()
                file_mtime = file_stat.st_mtime
                file_path_str = str(file_path)
                # Use execute() for get_file_by_path
                file_result = database.execute(
                    """
                    SELECT id, path, last_modified FROM files
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
                    # Use execute() for add_file
                    file_lines = len(file_path.read_text(encoding="utf-8").splitlines())
                    database.execute(
                        """
                        INSERT INTO files (path, lines, last_modified, has_docstring, project_id, dataset_id, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, julianday('now'))
                        """,
                        (
                            file_path_str,
                            file_lines,
                            file_mtime,
                            False,
                            self.project_id,
                            dataset_id,
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
