"""
Queue phase: batch DB operations for file changes (new/changed/deleted).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .processor_delta import FileDelta

logger = logging.getLogger(__name__)


class ProcessorQueueOps:
    """Queue file changes for multiple projects (batch DB operations)."""

    def __init__(
        self,
        database: Any,
        watch_dirs_resolved: List[Path],
    ) -> None:
        self.database = database
        self.watch_dirs_resolved = watch_dirs_resolved

    def _db_execute(self, sql: str, params: Optional[tuple] = None) -> Any:
        """Execute SQL; support both execute() (client) and _execute() (CodeDatabase)."""
        if hasattr(self.database, "execute"):
            return self.database.execute(sql, params or ())
        self.database._execute(sql, params)
        result = getattr(self.database, "_last_execute_result", None)
        if result is not None:
            return result
        # CodeDatabase with db_driver: _execute returns None; use _fetchone for SELECT
        if hasattr(self.database, "_fetchone") and sql.strip().upper().startswith(
            "SELECT"
        ):
            row = self.database._fetchone(sql, params)
            return {"data": [row]} if row else {"data": []}
        return {"data": []}

    def _db_execute_batch(
        self,
        operations: List[Tuple[str, Optional[tuple]]],
    ) -> List[Dict[str, Any]]:
        """Run multiple SQL operations in one batch if database supports it."""
        if not operations:
            return []
        if hasattr(self.database, "execute_batch"):
            return self.database.execute_batch(operations)
        results: List[Dict[str, Any]] = []
        for sql, params in operations:
            self._db_execute(sql, params or ())
            results.append({"data": []})
        return results

    def queue_changes(
        self, root_dir: Path, deltas: Dict[str, FileDelta]
    ) -> Dict[str, Any]:
        """Queue file changes for multiple projects. Returns aggregated statistics."""
        total_stats = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }

        for project_id, delta in deltas.items():
            try:
                project_obj = self.database.get_project(project_id)
                # get_project may return a dict (local DB) or a Project object (RPC client)
                if not project_obj:
                    project = None
                else:
                    # Use attribute access for Project, subscript for dict (avoid TypeError)
                    id_ = (
                        project_obj["id"]
                        if isinstance(project_obj, dict)
                        else getattr(project_obj, "id", None)
                    )
                    root_path = (
                        project_obj["root_path"]
                        if isinstance(project_obj, dict)
                        else getattr(project_obj, "root_path", None)
                    )
                    name = (
                        project_obj.get("name")
                        if isinstance(project_obj, dict)
                        else getattr(project_obj, "name", None)
                    )
                    project = {"id": id_, "root_path": root_path, "name": name}
                root_path_val = project.get("root_path") if project else None
                if not project or not root_path_val:
                    logger.error(
                        f"[QUEUE] Project {project_id} not found in database. Skipping."
                    )
                    total_stats["errors"] += (
                        len(delta.new_files)
                        + len(delta.changed_files)
                        + len(delta.deleted_files)
                    )
                    continue

                project_root = Path(root_path_val)
                project_stats = self._queue_project_delta(
                    project_id, delta, project_root
                )
                total_stats["new_files"] += project_stats["new_files"]
                total_stats["changed_files"] += project_stats["changed_files"]
                total_stats["deleted_files"] += project_stats["deleted_files"]
                total_stats["errors"] += project_stats["errors"]

            except Exception as e:
                logger.error(
                    f"Error queueing changes for project {project_id} in {root_dir}: {e}",
                    exc_info=True,
                )
                total_stats["errors"] += (
                    len(delta.new_files)
                    + len(delta.changed_files)
                    + len(delta.deleted_files)
                )

        return total_stats

    def _queue_project_delta(
        self, project_id: str, delta: FileDelta, project_root: Path
    ) -> Dict[str, Any]:
        """Queue file changes for a single project (batch INSERT/UPDATE where possible)."""
        from ..path_normalization import normalize_file_path
        from ..exceptions import ProjectIdMismatchError

        stats = {
            "new_files": 0,
            "changed_files": 0,
            "deleted_files": 0,
            "errors": 0,
        }
        watch_dirs: List[Path] = list(self.watch_dirs_resolved)

        # Collect (abs_path, lines, mtime, has_docstring, is_new) for batch when project_root is set
        batch_rows: List[Tuple[str, int, float, bool, bool]] = []

        def _collect_one(
            file_path_str: str, mtime: float, size: int, is_new: bool
        ) -> bool:
            try:
                normalized = normalize_file_path(
                    file_path_str,
                    watch_dirs=watch_dirs,
                    project_root=project_root,
                )
                if normalized.project_id != project_id:
                    raise ProjectIdMismatchError(
                        message=(
                            f"Project ID mismatch: file {normalized.absolute_path}"
                        ),
                        file_project_id=normalized.project_id,
                        db_project_id=project_id,
                    )
                abs_path = normalized.absolute_path
                path_obj = Path(abs_path)
                lines = 0
                has_docstring = False
                if path_obj.exists() and path_obj.is_file():
                    try:
                        text = path_obj.read_text(encoding="utf-8", errors="ignore")
                        lines = text.count("\n") + (1 if text else 0)
                        stripped = text.lstrip()
                        has_docstring = stripped.startswith(
                            '"""'
                        ) or stripped.startswith("'''")
                    except Exception:
                        pass
                batch_rows.append((abs_path, lines, mtime, has_docstring, is_new))
                return True
            except Exception as e:
                logger.debug(
                    "Skip batch for %s: %s",
                    file_path_str,
                    e,
                )
                return False
            return True

        for file_path_str, mtime, size in delta.new_files:
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(
                f"[project={project_id}] [NEW FILE] {file_path_str} | "
                f"mtime: {mtime_str} ({mtime}) | size: {size} bytes"
            )
            if not _collect_one(file_path_str, mtime, size, is_new=True):
                if self._queue_file_for_processing(
                    file_path_str, mtime, project_id, project_root
                ):
                    stats["new_files"] += 1
                else:
                    stats["errors"] += 1

        for file_path_str, mtime, size in delta.changed_files:
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(
                f"[project={project_id}] [CHANGED FILE] {file_path_str} | "
                f"mtime: {mtime_str} ({mtime}) | size: {size} bytes"
            )
            if not _collect_one(file_path_str, mtime, size, is_new=False):
                if self._queue_file_for_processing(
                    file_path_str, mtime, project_id, project_root
                ):
                    stats["changed_files"] += 1
                else:
                    stats["errors"] += 1

        # Batch INSERT and UPDATE for collected rows
        if batch_rows:
            # UPSERT in place: INSERT OR REPLACE deletes the row on conflict, which breaks FKs when
            # child tables (ast_trees, etc.) reference files(id) without ON DELETE CASCADE in DB.
            insert_sql = (
                "INSERT INTO files "
                "(path, lines, last_modified, has_docstring, project_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, julianday('now'), julianday('now')) "
                "ON CONFLICT (project_id, path) DO UPDATE SET "
                "lines = excluded.lines, "
                "last_modified = excluded.last_modified, "
                "has_docstring = excluded.has_docstring, "
                "deleted = FALSE, "
                "updated_at = julianday('now')"
            )
            update_sql = (
                "UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?"
            )
            insert_ops: List[Tuple[str, Optional[tuple]]] = [
                (insert_sql, (path, lines, mtime, has_docstring, project_id))
                for (path, lines, mtime, has_docstring, _) in batch_rows
            ]
            update_ops: List[Tuple[str, Optional[tuple]]] = [
                (update_sql, (path, project_id)) for (path, _, _, _, _) in batch_rows
            ]
            try:
                self._db_execute_batch(insert_ops)
                self._db_execute_batch(update_ops)
                for _, _, _, _, is_new in batch_rows:
                    if is_new:
                        stats["new_files"] += 1
                    else:
                        stats["changed_files"] += 1
            except Exception as e:
                logger.error(
                    "Batch queue failed for project %s: %s",
                    project_id,
                    e,
                    exc_info=True,
                )
                stats["errors"] += len(batch_rows)

        # Batch soft-delete for removed files
        if delta.deleted_files:
            delete_sql = (
                "UPDATE files SET deleted = TRUE, updated_at = julianday('now') "
                "WHERE path = ? AND project_id = ?"
            )
            delete_ops: List[Tuple[str, Optional[tuple]]] = [
                (delete_sql, (path, project_id)) for path in delta.deleted_files
            ]
            try:
                for path in delta.deleted_files:
                    logger.info(
                        f"[project={project_id}] [DELETED FILE] {path} | action: soft_delete"
                    )
                self._db_execute_batch(delete_ops)
                stats["deleted_files"] = len(delta.deleted_files)
            except Exception as e:
                logger.error(
                    "Batch delete failed for project %s: %s",
                    project_id,
                    e,
                    exc_info=True,
                )
                stats["errors"] += len(delta.deleted_files)

        return stats

    def _queue_file_for_processing(
        self,
        file_path: str,
        mtime: float,
        project_id: str,
        project_root: Optional[Path] = None,
    ) -> bool:
        """Queue file for processing (add/update in DB, mark needs_chunking)."""
        from ..path_normalization import normalize_file_path
        from ..exceptions import ProjectIdMismatchError

        try:
            watch_dirs: List[str | Path] = list(self.watch_dirs_resolved)
            normalized = normalize_file_path(
                file_path,
                watch_dirs=watch_dirs,
                project_root=project_root,
            )
            abs_file_path = normalized.absolute_path

            if normalized.project_id != project_id:
                raise ProjectIdMismatchError(
                    message=(
                        f"Project ID mismatch: file {abs_file_path} belongs to project "
                        f"{normalized.project_id} but was provided with project_id {project_id}"
                    ),
                    file_project_id=normalized.project_id,
                    db_project_id=project_id,
                )

            if project_root is None:
                project_root = normalized.project_root

            if not project_root:
                root_dir = self._get_project_root_dir(project_id, abs_file_path)
                if not root_dir:
                    logger.warning(
                        f"Could not determine root_dir for {abs_file_path}, "
                        "falling back to mark_file_needs_chunking"
                    )
                    res = self._db_execute(
                        "SELECT id FROM files WHERE path = ? AND project_id = ?",
                        (abs_file_path, project_id),
                    )
                    data = res.get("data", [])
                    existing = data[0] if data else None
                    if not existing:
                        path_obj = Path(abs_file_path)
                        lines = 0
                        has_docstring = False
                        try:
                            if path_obj.exists() and path_obj.is_file():
                                text = path_obj.read_text(
                                    encoding="utf-8", errors="ignore"
                                )
                                lines = text.count("\n") + (1 if text else 0)
                                stripped = text.lstrip()
                                has_docstring = stripped.startswith(
                                    '"""'
                                ) or stripped.startswith("'''")
                        except Exception:
                            logger.debug(
                                f"[QUEUE] Failed to read file for metadata: {abs_file_path}"
                            )
                        try:
                            self._db_execute(
                                """
                                INSERT INTO files (path, lines, last_modified, has_docstring, project_id, created_at)
                                VALUES (?, ?, ?, ?, ?, julianday('now'))
                                """,
                                (
                                    abs_file_path,
                                    lines,
                                    mtime,
                                    has_docstring,
                                    project_id,
                                ),
                            )
                        except Exception as e:
                            logger.error(
                                f"[QUEUE] Failed to add new file: {abs_file_path} ({e})"
                            )
                            return False
                        self._db_execute(
                            """
                            UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?
                            """,
                            (abs_file_path, project_id),
                        )
                    else:
                        self._db_execute(
                            """
                            UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?
                            """,
                            (abs_file_path, project_id),
                        )
                    return True

            if project_root:
                logger.debug(
                    f"[QUEUE] File normalized: file={abs_file_path}, project_root={project_root}, project_id={project_id}"
                )

            path_obj = Path(abs_file_path)
            lines = 0
            has_docstring = False
            try:
                if path_obj.exists() and path_obj.is_file():
                    text = path_obj.read_text(encoding="utf-8", errors="ignore")
                    lines = text.count("\n") + (1 if text else 0)
                    stripped = text.lstrip()
                    has_docstring = stripped.startswith('"""') or stripped.startswith(
                        "'''"
                    )
            except Exception:
                logger.debug(
                    f"[QUEUE] Failed to read file for metadata: {abs_file_path}"
                )

            try:
                self._db_execute(
                    """
                    INSERT INTO files (path, lines, last_modified, has_docstring, project_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, julianday('now'), julianday('now'))
                    ON CONFLICT (project_id, path) DO UPDATE SET
                    lines = excluded.lines,
                    last_modified = excluded.last_modified,
                    has_docstring = excluded.has_docstring,
                    deleted = FALSE,
                    updated_at = julianday('now')
                    """,
                    (
                        abs_file_path,
                        lines,
                        mtime,
                        has_docstring,
                        project_id,
                    ),
                )
                res = self._db_execute(
                    "SELECT id FROM files WHERE path = ? AND project_id = ? LIMIT 1",
                    (abs_file_path, project_id),
                )
                data = res.get("data", [])
                file_row = data[0] if data else None
                file_id = file_row.get("id", 0) if file_row else 0
                logger.debug(
                    f"[QUEUE] File added/updated: {abs_file_path} | file_id={file_id} | project_id={project_id}"
                )

                file_record = self.database.get_file_by_id(file_id) if file_id else None
                if not file_record:
                    logger.error(
                        f"[QUEUE] File file_id={file_id} not found after add: {abs_file_path}"
                    )
                    return False
                logger.debug(
                    f"[QUEUE] File verified: file_id={file_id}, path={file_record.get('path')}"
                )
            except Exception as e:
                logger.error(
                    f"[QUEUE] Failed to add/update file: {abs_file_path} ({e})",
                    exc_info=True,
                )
                return False

            logger.debug(
                f"[QUEUE] Marking for processing: file_id={file_id}, path={abs_file_path}"
            )
            self._db_execute(
                """
                UPDATE files SET needs_chunking = 1 WHERE path = ? AND project_id = ?
                """,
                (abs_file_path, project_id),
            )
            logger.debug(f"[QUEUE] File marked for vectorization: {abs_file_path}")
            return True

        except Exception as e:
            logger.error(
                f"[QUEUE] ✗ Error queueing file {file_path}: {e}",
                exc_info=True,
            )
            return False

    def _get_project_root_dir(self, project_id: str, file_path: str) -> Optional[Path]:
        """Get project root directory for a file."""
        try:
            project_obj = self.database.get_project(project_id)
            root = (
                project_obj.get("root_path")
                if isinstance(project_obj, dict)
                else getattr(project_obj, "root_path", None)
            )
            if root:
                return Path(root)
            abs_path = Path(file_path).resolve()
            for watch_dir in self.watch_dirs_resolved:
                try:
                    abs_path.relative_to(watch_dir)
                    return watch_dir
                except ValueError:
                    continue
            return None
        except Exception as e:
            logger.error(f"Error getting project root dir: {e}", exc_info=True)
            return None
