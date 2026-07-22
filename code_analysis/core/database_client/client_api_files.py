"""
File operations API methods for database client.

Provides object-oriented API methods for File operations.
File trash (mark/unmark/hard_delete/get_deleted_files) is aligned with
FILE_TRASH_SPEC step 12: mark uses trash_dir; unmark returns target-exists
via out_error; batch restore is done by command layer calling unmark in a loop.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.core.sql_portable import (
    WHERE_FILES_ACTIVE,
    sql_julian_timestamp_now_expr,
)

from .client_base import _DatabaseClientBase
from .objects.file import File
from .objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)

logger = logging.getLogger(__name__)


class _ClientAPIFilesMixin(_DatabaseClientBase):
    """Mixin class with File operation methods."""

    def create_file(self, file: File) -> File:
        """Create new file in database.

        Args:
            file: File object to create

        Returns:
            Created File object with ID and updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If file data is invalid
        """
        table_name = get_table_name_for_object(file)
        if table_name is None:
            raise ValueError("Unknown table for File object")

        data = object_to_db_row(file)
        self.insert(table_name, data)

        # Fetch created file to get all fields including ID and timestamps
        rows = self.select(
            table_name,
            where={
                "project_id": file.project_id,
                "path": file.path,
            },
        )
        if not rows:
            raise ValueError(
                f"Failed to create file {file.path} in project {file.project_id}"
            )

        return db_row_to_object(rows[0], File)

    def get_file(self, file_id: int) -> Optional[File]:
        """Get file by ID.

        Args:
            file_id: File identifier

        Returns:
            File object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("files", where={"id": file_id})
        if not rows:
            return None

        return db_row_to_object(rows[0], File)

    def get_file_by_id(self, file_id: int) -> Optional[Dict[str, Any]]:
        """Get file record by ID as dict (for compatibility with processor).

        Args:
            file_id: File identifier

        Returns:
            Row as dict with id, path, last_modified, etc., or None if not found.
        """
        rows = self.select("files", where={"id": file_id})
        return rows[0] if rows else None

    def get_file_by_path(
        self, path: str, project_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Resolve a filesystem path to a file row (project-relative or legacy absolute)."""
        from code_analysis.core.path_normalization import normalize_path_simple
        from code_analysis.core.file_identity import (
            FILE_ROW_PATH_MATCH_SQL,
            file_row_path_match_values,
        )

        abs_path = normalize_path_simple(path)
        project = self.get_project(project_id)
        if not project:
            return None
        root = project.root_path
        active = "" if include_deleted else f" AND {WHERE_FILES_ACTIVE}"
        try:
            r1, r2, r3 = file_row_path_match_values(
                project_root=root, absolute_path=abs_path
            )
        except ValueError:
            result = self.execute(
                f"SELECT * FROM files WHERE project_id = ? AND path = ?{active}",
                (project_id, abs_path),
            )
            rows = result.get("data", []) if isinstance(result, dict) else []
            return rows[0] if rows else None

        result = self.execute(
            f"SELECT * FROM files WHERE project_id = ? AND {FILE_ROW_PATH_MATCH_SQL}"
            f"{active}",
            (project_id, r1, r2, r3),
        )
        rows = result.get("data", []) if isinstance(result, dict) else []
        return rows[0] if rows else None

    def add_file(
        self,
        path: str,
        lines: int,
        last_modified: float,
        has_docstring: bool,
        project_id: str,
    ) -> str:
        """Add or update file record. Returns file id (UUID string when DB uses UUID PK).

        Path must be absolute. If file exists for this project, updates it.
        Uses atomic INSERT OR REPLACE to avoid TOCTOU race between get and insert.

        Args:
            path: Absolute file path.
            lines: Number of lines.
            last_modified: Modification timestamp.
            has_docstring: Whether file has docstring.
            project_id: Project UUID.

        Returns:
            File primary key as string (UUID for UUID ``files.id``; coerced for legacy int PK).
        """
        from code_analysis.core.file_identity import relative_path_for_project
        from code_analysis.core.path_normalization import normalize_path_simple

        abs_path = normalize_path_simple(path)
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        raw_root = getattr(project, "root_path", None)
        # A project whose root cannot be resolved on disk yields an empty (or
        # relative) root_path. Path("").resolve() would silently collapse to the
        # server's working directory (/usr/lib/casmgr-server) and every file would
        # fail "not within project root" against the install dir. Fail loudly with
        # the real cause instead (startup reconciliation purges such orphans).
        if not raw_root or not Path(raw_root).is_absolute():
            raise ValueError(
                f"Project {project_id} root_path is unresolved "
                f"({raw_root!r}); cannot index files for it"
            )
        root = Path(raw_root).resolve()
        relative_path_str = relative_path_for_project(abs_path, root)
        watch_dir_id = getattr(project, "watch_dir_id", None)
        _now = sql_julian_timestamp_now_expr(self)
        existing = self.get_file_by_path(abs_path, project_id, include_deleted=False)
        if existing:
            file_id_raw = existing.get("id")
            if file_id_raw is None:
                self.execute(
                    "DELETE FROM files WHERE project_id = ? AND (path = ? OR relative_path = ? OR path = ?)",
                    (project_id, abs_path, relative_path_str, relative_path_str),
                )
            else:
                file_id = str(file_id_raw)
                self.execute(
                    f"""
                    UPDATE files
                    SET watch_dir_id = ?, path = ?, relative_path = ?, lines = ?,
                        last_modified = ?, has_docstring = ?, updated_at = {_now}
                    WHERE id = ?
                    """,
                    (
                        watch_dir_id,
                        abs_path,
                        relative_path_str,
                        lines,
                        last_modified,
                        bool(has_docstring),
                        file_id,
                    ),
                )
                return file_id

        # Soft-deleted row still holds UNIQUE (project_id, path); get_file_by_path(...,
        # include_deleted=False) hides it and a plain INSERT violates the constraint.
        tombstone = self.get_file_by_path(abs_path, project_id, include_deleted=True)
        if tombstone:
            file_id_raw = tombstone.get("id")
            if file_id_raw is None:
                self.execute(
                    "DELETE FROM files WHERE project_id = ? AND (path = ? OR relative_path = ? OR path = ?)",
                    (project_id, abs_path, relative_path_str, relative_path_str),
                )
            else:
                file_id = str(file_id_raw)
                self.execute(
                    f"""
                    UPDATE files
                    SET watch_dir_id = ?, path = ?, relative_path = ?, lines = ?,
                        last_modified = ?, has_docstring = ?, deleted = 0,
                        updated_at = {_now}
                    WHERE id = ?
                    """,
                    (
                        watch_dir_id,
                        abs_path,
                        relative_path_str,
                        lines,
                        last_modified,
                        bool(has_docstring),
                        file_id,
                    ),
                )
                return file_id

        new_id = str(uuid.uuid4())
        self.execute(
            f"""
            INSERT INTO files
            (id, project_id, watch_dir_id, path, relative_path, lines,
             last_modified, has_docstring, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, {_now})
            """,
            (
                new_id,
                project_id,
                watch_dir_id,
                abs_path,
                relative_path_str,
                lines,
                last_modified,
                bool(has_docstring),
            ),
        )
        return new_id

    def add_code_content(
        self,
        file_id: int,
        entity_type: str,
        entity_name: str,
        content: str,
        docstring: Optional[str],
        entity_id: Optional[int] = None,
    ) -> int:
        """Add code content. Returns content id.

        PostgreSQL has no ``code_content_fts`` (FTS5 virtual table); fulltext
        search runs directly over ``code_content`` via tsvector.
        """
        result = self.execute(
            "INSERT INTO code_content (file_id, entity_type, entity_id, entity_name, content, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, entity_type, entity_id, entity_name, content, docstring),
        )
        row_id = result.get("lastrowid") or 0
        return row_id

    def add_class(
        self,
        file_id: int,
        name: str,
        line: int,
        docstring: Optional[str],
        bases: List[str],
        end_line: Optional[int] = None,
        cst_node_id: Optional[str] = None,
    ) -> int:
        """Add or replace class. Returns class id."""
        bases_json = json.dumps(bases)
        result = self.execute(
            "INSERT OR REPLACE INTO classes (file_id, name, line, end_line, cst_node_id, docstring, bases) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (file_id, name, line, end_line, cst_node_id, docstring, bases_json),
        )
        return result.get("lastrowid", 0) or 0

    def add_method(
        self,
        class_id: int,
        name: str,
        line: int,
        args: List[str],
        docstring: Optional[str],
        complexity: Optional[int] = None,
        end_line: Optional[int] = None,
        cst_node_id: Optional[str] = None,
    ) -> int:
        """Add or replace method. Returns method id."""
        args_json = json.dumps(args)
        result = self.execute(
            "INSERT OR REPLACE INTO methods (class_id, name, line, end_line, cst_node_id, args, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (class_id, name, line, end_line, cst_node_id, args_json, docstring),
        )
        return result.get("lastrowid", 0) or 0

    def add_function(
        self,
        file_id: int,
        name: str,
        line: int,
        args: List[str],
        docstring: Optional[str],
        complexity: Optional[int] = None,
        end_line: Optional[int] = None,
        cst_node_id: Optional[str] = None,
    ) -> int:
        """Add or replace function. Returns function id."""
        args_json = json.dumps(args)
        result = self.execute(
            "INSERT OR REPLACE INTO functions (file_id, name, line, end_line, cst_node_id, args, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (file_id, name, line, end_line, cst_node_id, args_json, docstring),
        )
        return result.get("lastrowid", 0) or 0

    def add_import(
        self,
        file_id: int,
        name: str,
        module: Optional[str],
        import_type: str,
        line: int,
    ) -> int:
        """Add import. Returns import id."""
        result = self.execute(
            "INSERT INTO imports (file_id, name, module, import_type, line) "
            "VALUES (?, ?, ?, ?, ?)",
            (file_id, name, module, import_type, line),
        )
        return result.get("lastrowid", 0) or 0

    def add_usage(
        self,
        file_id: int,
        line: int,
        usage_type: str,
        target_type: str,
        target_name: str,
        target_class: Optional[str] = None,
        context: Optional[str] = None,
    ) -> int:
        """Add usage record. Returns usage id."""
        result = self.execute(
            "INSERT INTO usages (file_id, line, usage_type, target_type, target_name, target_class, context) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                file_id,
                line,
                usage_type,
                target_type,
                target_name,
                target_class,
                context,
            ),
        )
        return result.get("lastrowid", 0) or 0

    def mark_file_needs_chunking(self, file_path: str, project_id: str) -> bool:
        """Mark file for re-chunking by deleting its chunks. ``file_path`` may be absolute."""
        from code_analysis.core.path_normalization import normalize_path_simple

        abs_path = normalize_path_simple(file_path)
        row = self.get_file_by_path(abs_path, project_id, include_deleted=True)
        if not row:
            return False
        if row.get("deleted"):
            return False
        file_id = row.get("id")
        if file_id is None:
            return False
        self.execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
        _now = sql_julian_timestamp_now_expr(self)
        self.execute(
            f"UPDATE files SET needs_chunking = 1, updated_at = {_now} WHERE id = ?",
            (file_id,),
        )
        return True

    def update_file(self, file: File) -> File:
        """Update existing file in database.

        Args:
            file: File object with updated data

        Returns:
            Updated File object

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If file not found
        """
        if file.id is None:
            raise ValueError("File id is required for update")

        # Check if file exists
        existing = self.get_file(file.id)
        if existing is None:
            raise ValueError(f"File {file.id} not found")

        # Update file
        data = object_to_db_row(file)
        # Remove id from update data (it's in where clause)
        update_data = {k: v for k, v in data.items() if k != "id"}
        self.update("files", where={"id": file.id}, data=update_data)

        # Fetch updated file
        return self.get_file(file.id) or file

    def get_project_file_rows(
        self, project_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """Get file rows for a project with raw last_modified (no Julian parsing).

        Used by the file watcher so last_modified is compared as Unix timestamp
        against os.stat().st_mtime. get_project_files() parses last_modified as
        Julian and breaks the comparison, causing mass false 'changed' detection.

        Args:
            project_id: Project identifier
            include_deleted: Whether to include deleted files

        Returns:
            List of dicts with id, path, last_modified (raw from DB)
        """
        where = {"project_id": project_id}
        if not include_deleted:
            where["deleted"] = 0
        rows = self.select("files", where=where, order_by=["path"])
        return list(rows) if rows else []

    def get_project_files(
        self,
        project_id: str,
        include_deleted: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[File]:
        """Get files for a project, optionally paginated.

        Args:
            project_id: Project identifier
            include_deleted: Whether to include deleted files
            limit: Maximum number of files to return (None = all)
            offset: Number of files to skip (0 = from start)

        Returns:
            List of File objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        where = {"project_id": project_id}
        if not include_deleted:
            where["deleted"] = 0

        rows = self.select(
            "files",
            where=where,
            order_by=["path"],
            limit=limit,
            offset=offset,
        )
        return db_rows_to_objects(rows, File)

    def index_file(
        self,
        file_path: str,
        project_id: str,
        *,
        priority: int = 0,
        docs_indexing: Optional[Dict[str, Any]] = None,
        server_config_path: Optional[str] = None,
        skip_file_edit_lock: bool = False,
    ) -> Dict[str, Any]:
        """Request full file index (AST, CST, entities, code_content) via driver RPC.

        Project root is resolved from the database (projects.root_path). On success,
        the driver clears needs_chunking for the file.

        Args:
            file_path: Absolute path to the file (as stored in files.path)
            project_id: Project UUID
            priority: Non-zero tags background/heavy callers on the RPC request
            docs_indexing: When set, enables documentation file path in ``analyze_file``
                (``.md``, ``.json``, ``.yaml``, ``.yml`` per eligibility).
            server_config_path: Server ``config.json`` for optional SVO chunking (docs path).
            skip_file_edit_lock: When True, caller already holds ``files.editing_pid``.

        Returns:
            Update result dict: success, file_id, file_path, ast_updated, cst_updated,
            entities_updated, or error message on failure

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If driver returns an error
        """
        payload: Dict[str, Any] = {
            "file_path": file_path,
            "project_id": project_id,
        }
        if docs_indexing is not None:
            payload["docs_indexing"] = docs_indexing
        if server_config_path:
            payload["server_config_path"] = server_config_path
        if skip_file_edit_lock:
            payload["skip_file_edit_lock"] = True
        response = self.rpc_client.call(
            "index_file",
            payload,
            priority=priority,
        )
        result = self._extract_result_data(response)
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return result if isinstance(result, dict) else {}

    def mark_file_deleted(
        self,
        file_path: str,
        project_id: str,
        version_dir: Optional[str] = None,
        reason: Optional[str] = None,
        trash_dir: Optional[str] = None,
    ) -> bool:
        """Mark file as deleted (soft delete) and move to file trash. FILE_TRASH_SPEC step 12.

        Path resolution: project root is taken from the projects table in the driver DB;
        relative file_path is resolved against that root.

        Args:
            file_path: Original file path (relative to project root or absolute).
            project_id: Project UUID.
            version_dir: Legacy version directory (used when trash_dir is None).
            reason: Optional reason for deletion.
            trash_dir: Preferred file trash root; files go under trash_dir/project_id/...

        Returns:
            True if file was found and marked, False otherwise.

        Raises:
            RPCClientError: If RPC call fails.
            RPCResponseError: If driver returns an error.
        """
        params: Dict[str, Any] = {"file_path": file_path, "project_id": project_id}
        if version_dir is not None:
            params["version_dir"] = version_dir
        if reason is not None:
            params["reason"] = reason
        if trash_dir is not None:
            params["trash_dir"] = trash_dir
        response = self.rpc_client.call("mark_file_deleted", params)
        result = self._extract_result_data(response)
        if isinstance(result, dict) and "data" in result:
            return result["data"].get("success", False)
        return False

    def unmark_file_deleted(
        self,
        file_path: str,
        project_id: str,
        out_error: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Unmark file as deleted (restore from trash). FILE_TRASH_SPEC step 12.

        Args:
            file_path: Current path (in trash) or original_path to search.
            project_id: Project UUID.
            out_error: Optional dict to receive error_code and message when returning False.

        Returns:
            True if file was restored, False otherwise (e.g. FILE_EXISTS_AT_TARGET).
        """
        params = {"file_path": file_path, "project_id": project_id}
        response = self.rpc_client.call("unmark_file_deleted", params)
        result = self._extract_result_data(response)
        if not isinstance(result, dict) or "data" not in result:
            return False
        data = result["data"]
        success = data.get("success", False)
        if not success and out_error is not None:
            if "error_code" in data:
                out_error["error_code"] = data["error_code"]
            if "message" in data:
                out_error["message"] = data["message"]
        return success

    def hard_delete_file(self, file_id: str | int) -> None:
        """Permanently delete file and all related data (hard delete). FILE_TRASH_SPEC step 12.

        Args:
            file_id: File primary key (UUID string or legacy integer).

        Raises:
            RPCClientError: If RPC call fails.
            RPCResponseError: If driver returns an error.
        """
        response = self.rpc_client.call("hard_delete_file", {"file_id": file_id})
        self._extract_result_data(response)

    def get_deleted_files(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all deleted files for a project (path = trash path). FILE_TRASH_SPEC step 12.

        Args:
            project_id: Project UUID.

        Returns:
            List of deleted file records (path is path in trash).
        """
        response = self.rpc_client.call("get_deleted_files", {"project_id": project_id})
        result = self._extract_result_data(response)
        if isinstance(result, dict) and "data" in result:
            return result["data"] if isinstance(result["data"], list) else []
        return []
