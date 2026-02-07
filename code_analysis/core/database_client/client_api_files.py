"""
File operations API methods for database client.

Provides object-oriented API methods for File operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .objects.file import File
from .objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)

logger = logging.getLogger(__name__)


class _ClientAPIFilesMixin:
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
        """Get file record by path and project ID.

        Args:
            path: File path (absolute; must match path stored in database).
            project_id: Project identifier.
            include_deleted: If True, include files marked as deleted.

        Returns:
            Row as dict with id, path, last_modified, etc., or None if not found.
        """
        where: Dict[str, Any] = {"path": path, "project_id": project_id}
        if not include_deleted:
            where["deleted"] = 0
        rows = self.select("files", where=where)
        return rows[0] if rows else None

    def add_file(
        self,
        path: str,
        lines: int,
        last_modified: float,
        has_docstring: bool,
        project_id: str,
    ) -> int:
        """Add or update file record. Returns file_id.

        Path must be absolute. If file exists for this project, updates it.
        Simplified client implementation; does not handle cross-project moves.

        Args:
            path: Absolute file path.
            lines: Number of lines.
            last_modified: Modification timestamp.
            has_docstring: Whether file has docstring.
            project_id: Project UUID.

        Returns:
            File ID (existing or newly inserted).
        """
        abs_path = str(Path(path).resolve())
        project = self.get_project(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")
        root = Path(project.root_path).resolve()
        try:
            relative_path = Path(abs_path).relative_to(root)
        except ValueError:
            relative_path = Path(abs_path).name
        watch_dir_id = getattr(project, "watch_dir_id", None)
        existing = self.get_file_by_path(abs_path, project_id)
        if existing:
            file_id = existing["id"]
            self.update(
                "files",
                where={"id": file_id},
                data={
                    "path": abs_path,
                    "relative_path": str(relative_path),
                    "lines": lines,
                    "last_modified": last_modified,
                    "has_docstring": 1 if has_docstring else 0,
                    "watch_dir_id": watch_dir_id,
                },
            )
            return file_id
        data: Dict[str, Any] = {
            "project_id": project_id,
            "path": abs_path,
            "relative_path": str(relative_path),
            "lines": lines,
            "last_modified": last_modified,
            "has_docstring": 1 if has_docstring else 0,
            "deleted": 0,
        }
        if watch_dir_id is not None:
            data["watch_dir_id"] = watch_dir_id
        new_id = self.insert("files", data)
        return new_id if new_id else 0

    def save_ast_tree(
        self,
        file_id: int,
        project_id: str,
        ast_json: str,
        ast_hash: str,
        file_mtime: float,
        overwrite: bool = False,
    ) -> int:
        """Save AST tree for a file. Returns ast_tree id."""
        if overwrite:
            self.execute(
                "DELETE FROM ast_trees WHERE file_id = ?",
                (file_id,),
            )
        if not overwrite:
            result = self.execute(
                "SELECT id FROM ast_trees WHERE file_id = ? AND ast_hash = ?",
                (file_id, ast_hash),
            )
            rows = result.get("data", [])
            if rows:
                existing_id = rows[0].get("id")
                self.execute(
                    "UPDATE ast_trees SET ast_json = ?, file_mtime = ?, "
                    "updated_at = julianday('now') WHERE id = ?",
                    (ast_json, file_mtime, existing_id),
                )
                return existing_id
        result = self.execute(
            "INSERT INTO ast_trees (file_id, project_id, ast_json, ast_hash, file_mtime) "
            "VALUES (?, ?, ?, ?, ?)",
            (file_id, project_id, ast_json, ast_hash, file_mtime),
        )
        return result.get("lastrowid", 0) or 0

    def save_cst_tree(
        self,
        file_id: int,
        project_id: str,
        cst_code: str,
        cst_hash: str,
        file_mtime: float,
        overwrite: bool = False,
    ) -> int:
        """Save CST tree (source code) for a file. Returns cst_tree id."""
        if overwrite:
            self.execute(
                "DELETE FROM cst_trees WHERE file_id = ?",
                (file_id,),
            )
        if not overwrite:
            result = self.execute(
                "SELECT id FROM cst_trees WHERE file_id = ? AND cst_hash = ?",
                (file_id, cst_hash),
            )
            rows = result.get("data", [])
            if rows:
                existing_id = rows[0].get("id")
                self.execute(
                    "UPDATE cst_trees SET cst_code = ?, file_mtime = ?, "
                    "updated_at = julianday('now') WHERE id = ?",
                    (cst_code, file_mtime, existing_id),
                )
                return existing_id
        result = self.execute(
            "INSERT INTO cst_trees (file_id, project_id, cst_code, cst_hash, file_mtime) "
            "VALUES (?, ?, ?, ?, ?)",
            (file_id, project_id, cst_code, cst_hash, file_mtime),
        )
        return result.get("lastrowid", 0) or 0

    def add_code_content(
        self,
        file_id: int,
        entity_type: str,
        entity_name: str,
        content: str,
        docstring: Optional[str],
        entity_id: Optional[int] = None,
    ) -> int:
        """Add code content and FTS row. Returns content id."""
        result = self.execute(
            "INSERT INTO code_content (file_id, entity_type, entity_id, entity_name, content, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, entity_type, entity_id, entity_name, content, docstring),
        )
        row_id = result.get("lastrowid") or 0
        try:
            self.execute(
                "INSERT INTO code_content_fts (rowid, entity_type, entity_name, content, docstring) "
                "VALUES (?, ?, ?, ?, ?)",
                (row_id, entity_type, entity_name, content, docstring or ""),
            )
        except Exception as e:
            logger.warning("Failed to add content to FTS index: %s", e)
        return row_id

    def add_class(
        self,
        file_id: int,
        name: str,
        line: int,
        docstring: Optional[str],
        bases: List[str],
        end_line: Optional[int] = None,
    ) -> int:
        """Add or replace class. Returns class id."""
        bases_json = json.dumps(bases)
        result = self.execute(
            "INSERT OR REPLACE INTO classes (file_id, name, line, end_line, docstring, bases) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, name, line, end_line, docstring, bases_json),
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
    ) -> int:
        """Add or replace method. Returns method id."""
        args_json = json.dumps(args)
        result = self.execute(
            "INSERT OR REPLACE INTO methods (class_id, name, line, end_line, args, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (class_id, name, line, end_line, args_json, docstring),
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
    ) -> int:
        """Add or replace function. Returns function id."""
        args_json = json.dumps(args)
        result = self.execute(
            "INSERT OR REPLACE INTO functions (file_id, name, line, end_line, args, docstring) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, name, line, end_line, args_json, docstring),
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
        """Mark file for re-chunking by deleting its chunks. Path must be absolute."""
        abs_path = str(Path(file_path).resolve())
        result = self.execute(
            "SELECT id, deleted FROM files WHERE project_id = ? AND path = ?",
            (project_id, abs_path),
        )
        rows = result.get("data", [])
        if not rows:
            return False
        file_id = rows[0].get("id")
        deleted = rows[0].get("deleted")
        if deleted:
            return False
        self.execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))
        self.execute(
            "UPDATE files SET updated_at = julianday('now') WHERE id = ?",
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

    def delete_file(self, file_id: int) -> bool:
        """Delete file from database.

        Args:
            file_id: File identifier

        Returns:
            True if file was deleted, False if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        affected_rows = self.delete("files", where={"id": file_id})
        return affected_rows > 0

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
        self, project_id: str, include_deleted: bool = False
    ) -> List[File]:
        """Get all files for a project.

        Args:
            project_id: Project identifier
            include_deleted: Whether to include deleted files

        Returns:
            List of File objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        where = {"project_id": project_id}
        if not include_deleted:
            where["deleted"] = 0

        rows = self.select("files", where=where, order_by=["path"])
        return db_rows_to_objects(rows, File)

    def index_file(self, file_path: str, project_id: str) -> Dict[str, Any]:
        """Request full file index (AST, CST, entities, code_content) via driver RPC.

        Project root is resolved from the database (projects.root_path). On success,
        the driver clears needs_chunking for the file.

        Args:
            file_path: Absolute path to the file (as stored in files.path)
            project_id: Project UUID

        Returns:
            Update result dict: success, file_id, file_path, ast_updated, cst_updated,
            entities_updated, or error message on failure

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If driver returns an error
        """
        response = self.rpc_client.call(
            "index_file",
            {"file_path": file_path, "project_id": project_id},
        )
        result = self._extract_result_data(response)
        if isinstance(result, dict) and "data" in result:
            return result["data"]
        return result if isinstance(result, dict) else {}
