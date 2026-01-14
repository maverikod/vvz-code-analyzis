"""
MCP command: compose_cst_module

Applies CST tree to file with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.backup_manager import BackupManager
from ..core.git_integration import create_git_commit
from ..core.cst_tree.tree_builder import get_tree

logger = logging.getLogger(__name__)


class ComposeCSTModuleCommand(BaseMCPCommand):
    """
    Compose/patch a module using CST tree.

    Process:
    1. Get CST tree from tree_id
    2. Generate source code from tree
    3. Write to temporary file
    4. Validate temporary file (compile)
    5. If validation fails, return errors
    6. Check if file exists in database, backup data if exists
    7. Begin database transaction
    8. Delete all old data (clear_file_data)
    9. Add new data (update_file_data_atomic)
    10. Atomically replace file
    11. Commit transaction
    12. Git commit (if commit_message provided)
    13. On any error: rollback transaction and restore data from backup
    """

    name = "compose_cst_module"
    version = "2.0.0"
    descr = "Apply CST tree to file with atomic operations"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID (UUID4). Required.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (relative to project root)",
                },
                "tree_id": {
                    "type": "string",
                    "description": "CST tree ID from cst_load_file command",
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional git commit message",
                },
            },
            "required": ["project_id", "file_path", "tree_id"],
            "additionalProperties": False,
        }

    def _backup_file_data(self, database, file_id: int) -> Optional[Dict[str, Any]]:
        """
        Backup all file data from database.

        Args:
            database: Database instance
            file_id: File ID

        Returns:
            Dictionary with backed up data or None if file not found
        """
        # Get file record
        file_record = database.get_file_by_id(file_id)
        if not file_record:
            return None

        # Use DatabaseClient API
        classes_result = database.execute(
            "SELECT * FROM classes WHERE file_id = ?", (file_id,)
        )
        functions_result = database.execute(
            "SELECT * FROM functions WHERE file_id = ?", (file_id,)
        )
        imports_result = database.execute(
            "SELECT * FROM imports WHERE file_id = ?", (file_id,)
        )
        usages_result = database.execute(
            "SELECT * FROM usages WHERE file_id = ?", (file_id,)
        )
        issues_result = database.execute(
            "SELECT * FROM issues WHERE file_id = ?", (file_id,)
        )
        code_content_result = database.execute(
            "SELECT * FROM code_content WHERE file_id = ?", (file_id,)
        )
        ast_trees_result = database.execute(
            "SELECT * FROM ast_trees WHERE file_id = ?", (file_id,)
        )
        cst_trees_result = database.execute(
            "SELECT * FROM cst_trees WHERE file_id = ?", (file_id,)
        )

        backup_data = {
            "file_record": file_record,
            "classes": classes_result.get("data", []),
            "functions": functions_result.get("data", []),
            "imports": imports_result.get("data", []),
            "usages": usages_result.get("data", []),
            "issues": issues_result.get("data", []),
            "code_content": code_content_result.get("data", []),
            "ast_trees": ast_trees_result.get("data", []),
            "cst_trees": cst_trees_result.get("data", []),
        }

        # Get methods for all classes
        class_ids = [row["id"] for row in backup_data["classes"]]
        if class_ids:
            placeholders = ",".join("?" * len(class_ids))
            methods_result = database.execute(
                f"SELECT * FROM methods WHERE class_id IN ({placeholders})",
                tuple(class_ids),
            )
            backup_data["methods"] = methods_result.get("data", [])
        else:
            backup_data["methods"] = []

            return backup_data

    def _delete_file_data(self, database, file_id: int) -> None:
        """
        Delete all file data within transaction.

        Args:
            database: Database instance
            file_id: File ID
        """
        # Get class and content IDs
        class_result = database.execute(
            "SELECT id FROM classes WHERE file_id = ?", (file_id,)
        )
        class_ids = [row["id"] for row in class_result.get("data", [])]
        content_result = database.execute(
            "SELECT id FROM code_content WHERE file_id = ?", (file_id,)
        )
        content_ids = [row["id"] for row in content_result.get("data", [])]

        # Delete FTS index
        if content_ids:
            placeholders = ",".join("?" * len(content_ids))
            database.execute(
                f"DELETE FROM code_content_fts WHERE rowid IN ({placeholders})",
                tuple(content_ids),
            )

        # Delete methods
        if class_ids:
            placeholders = ",".join("?" * len(class_ids))
            database.execute(
                f"DELETE FROM methods WHERE class_id IN ({placeholders})",
                tuple(class_ids),
            )

        # Delete main entities
        database.execute("DELETE FROM classes WHERE file_id = ?", (file_id,))
        database.execute("DELETE FROM functions WHERE file_id = ?", (file_id,))
        database.execute("DELETE FROM imports WHERE file_id = ?", (file_id,))
        database.execute("DELETE FROM issues WHERE file_id = ?", (file_id,))
        database.execute("DELETE FROM usages WHERE file_id = ?", (file_id,))
        database.execute("DELETE FROM code_content WHERE file_id = ?", (file_id,))
        database.execute("DELETE FROM ast_trees WHERE file_id = ?", (file_id,))
        database.execute("DELETE FROM cst_trees WHERE file_id = ?", (file_id,))
        database.execute("DELETE FROM code_chunks WHERE file_id = ?", (file_id,))

        # Delete vector index
        database.execute(
            "DELETE FROM vector_index WHERE entity_type = 'file' AND entity_id = ?",
            (file_id,),
        )
        if class_ids:
            placeholders = ",".join("?" * len(class_ids))
            database.execute(
                f"""
                DELETE FROM vector_index
                WHERE entity_type IN ('class', 'function', 'method')
                AND entity_id IN ({placeholders})
                """,
                tuple(class_ids),
            )

    def _restore_entities(self, database, backup_data: Dict[str, Any]) -> None:
        """
        Restore entities (classes, methods, functions) from backup.

        Args:
            database: Database instance
            backup_data: Backed up data
        """
        # Restore classes
        for row in backup_data["classes"]:
            database.execute(
                """
                INSERT INTO classes (id, file_id, name, qualname, start_line, end_line, docstring, bases)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["file_id"],
                    row["name"],
                    row["qualname"],
                    row["start_line"],
                    row["end_line"],
                    row.get("docstring"),
                    row.get("bases"),
                ),
            )

        # Restore methods
        for row in backup_data["methods"]:
            database.execute(
                """
                INSERT INTO methods (id, class_id, name, qualname, start_line, end_line, docstring, parameters)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["class_id"],
                    row["name"],
                    row["qualname"],
                    row["start_line"],
                    row["end_line"],
                    row.get("docstring"),
                    row.get("parameters"),
                ),
            )

        # Restore functions
        for row in backup_data["functions"]:
            database.execute(
                """
                INSERT INTO functions (id, file_id, name, qualname, start_line, end_line, docstring, parameters)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["file_id"],
                    row["name"],
                    row["qualname"],
                    row["start_line"],
                    row["end_line"],
                    row.get("docstring"),
                    row.get("parameters"),
                ),
            )

    def _restore_metadata(self, database, backup_data: Dict[str, Any]) -> None:
        """
        Restore metadata (imports, usages, issues, content) from backup.

        Args:
            database: Database instance
            backup_data: Backed up data
        """
        # Restore imports
        for row in backup_data["imports"]:
            database.execute(
                """
                INSERT INTO imports (id, file_id, module, name, alias, import_type, line)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["file_id"],
                    row["module"],
                    row["name"],
                    row.get("alias"),
                    row["import_type"],
                    row["line"],
                ),
            )

        # Restore usages
        for row in backup_data["usages"]:
            database.execute(
                """
                INSERT INTO usages (id, file_id, entity_type, entity_name, line, column)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["file_id"],
                    row["entity_type"],
                    row["entity_name"],
                    row["line"],
                    row.get("column"),
                ),
            )

        # Restore issues
        for row in backup_data["issues"]:
            database.execute(
                """
                INSERT INTO issues (id, file_id, issue_type, message, line, column)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["file_id"],
                    row["issue_type"],
                    row["message"],
                    row["line"],
                    row.get("column"),
                ),
            )

        # Restore code_content
        for row in backup_data["code_content"]:
            database.execute(
                """
                INSERT INTO code_content (id, file_id, content, start_line, end_line)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["file_id"],
                    row["content"],
                    row["start_line"],
                    row["end_line"],
                ),
            )

    def _restore_trees(self, database, backup_data: Dict[str, Any]) -> None:
        """
        Restore AST and CST trees from backup.

        Args:
            database: Database instance
            backup_data: Backed up data
        """
        # Restore AST trees
        for row in backup_data["ast_trees"]:
            database.execute(
                """
                INSERT INTO ast_trees (id, file_id, project_id, ast_json, ast_hash, file_mtime)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["file_id"],
                    row["project_id"],
                    row["ast_json"],
                    row["ast_hash"],
                    row["file_mtime"],
                ),
            )

        # Restore CST trees
        for row in backup_data["cst_trees"]:
            database.execute(
                """
                INSERT INTO cst_trees (id, file_id, project_id, cst_code, cst_hash, file_mtime)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["file_id"],
                    row["project_id"],
                    row["cst_code"],
                    row["cst_hash"],
                    row["file_mtime"],
                ),
            )

    def _restore_file_data(
        self, database, file_id: int, backup_data: Dict[str, Any]
    ) -> None:
        """
        Restore file data from backup.

        Args:
            database: Database instance
            file_id: File ID
            backup_data: Backed up data
        """
        # Restore file record
        file_record = backup_data["file_record"]
        database.execute(
            """
            UPDATE files SET
                path = ?, lines = ?, last_modified = ?, has_docstring = ?,
                project_id = ?, dataset_id = ?, updated_at = julianday('now')
            WHERE id = ?
            """,
            (
                file_record["path"],
                file_record["lines"],
                file_record["last_modified"],
                file_record["has_docstring"],
                file_record["project_id"],
                file_record.get("dataset_id"),
                file_id,
            ),
        )

        # Restore entities
        self._restore_entities(database, backup_data)

        # Restore metadata
        self._restore_metadata(database, backup_data)

        # Restore trees
        self._restore_trees(database, backup_data)

    def _validate_and_write_temp(
        self, source_code: str, target_path: Path
    ) -> tuple[Path, ErrorResult | None]:
        """
        Write source code to temporary file and validate it.

        Args:
            source_code: Source code to write
            target_path: Target file path

        Returns:
            Tuple of (temp_file_path, error_result or None)
        """
        temp_fd, temp_path_str = tempfile.mkstemp(
            suffix=".py", prefix="cst_compose_", dir=target_path.parent
        )
        temp_file = Path(temp_path_str)

        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(source_code)
        except Exception as e:
            os.close(temp_fd)
            return (
                temp_file,
                ErrorResult(
                    message=f"Failed to write temporary file: {e}",
                    code="TEMP_FILE_ERROR",
                    details={"error": str(e)},
                ),
            )

        # Validate temporary file
        try:
            compile(source_code, str(temp_file), "exec")
        except SyntaxError as e:
            temp_file.unlink()
            return (
                temp_file,
                ErrorResult(
                    message=f"Generated code has syntax errors: {e}",
                    code="VALIDATION_ERROR",
                    details={"error": str(e), "line": e.lineno, "offset": e.offset},
                ),
            )

        return (temp_file, None)

    def _update_file_record(
        self,
        database,
        project_id: str,
        root_path: Path,
        target_path: Path,
        source_code: str,
        file_id: Optional[int],
    ) -> int:
        """
        Add or update file record in database.

        Args:
            database: Database instance
            project_id: Project ID
            root_path: Project root path
            target_path: Target file path
            source_code: Source code
            file_id: Existing file ID or None

        Returns:
            File ID
        """
        from .base_mcp_command import BaseMCPCommand

        dataset_id = BaseMCPCommand._get_or_create_dataset(
            database, project_id, root_path
        )

        lines = source_code.count("\n") + (1 if source_code else 0)
        stripped = source_code.lstrip()
        has_docstring = stripped.startswith('"""') or stripped.startswith("'''")

        if not file_id:
            import time

            file_id = database.add_file(
                path=str(target_path),
                lines=lines,
                last_modified=time.time(),
                has_docstring=has_docstring,
                project_id=project_id,
                dataset_id=dataset_id,
            )
        else:
            database.execute(
                """
                UPDATE files SET
                    lines = ?, has_docstring = ?, updated_at = julianday('now')
                WHERE id = ?
                """,
                (lines, has_docstring, file_id),
            )

        return file_id

    def _handle_rollback(
        self,
        database,
        file_id: Optional[int],
        file_data_backup: Optional[Dict[str, Any]],
        backup_uuid: Optional[str],
        backup_manager: Optional[BackupManager],
        root_path: Path,
        target_path: Path,
    ) -> None:
        """
        Handle rollback: restore file data and file from backup.

        Args:
            database: Database instance
            file_id: File ID
            file_data_backup: Backup of file data or None
            backup_uuid: Backup UUID or None
            backup_manager: BackupManager instance or None
            root_path: Project root path
            target_path: Target file path
        """
        # Restore file data from backup if backup exists
        if file_data_backup and file_id:
            try:
                database.begin_transaction()
                self._restore_file_data(database, file_id, file_data_backup)
                database.commit_transaction()
                logger.info(f"File data restored from backup for file_id={file_id}")
            except Exception as restore_error:
                logger.error(
                    f"Failed to restore file data: {restore_error}",
                    exc_info=True,
                )
                try:
                    database.rollback_transaction()
                except Exception:
                    pass

        # Restore file from backup if backup was created
        if backup_uuid and backup_manager and target_path.exists():
            try:
                rel_path = str(target_path.relative_to(root_path))
            except ValueError:
                rel_path = str(target_path)
            restore_success, restore_message = backup_manager.restore_file(
                rel_path, backup_uuid
            )
            if restore_success:
                logger.info(f"File restored from backup: {restore_message}")
            else:
                logger.error(f"Failed to restore file from backup: {restore_message}")

    def _apply_changes(
        self,
        database,
        project_id: str,
        root_path: Path,
        target_path: Path,
        source_code: str,
        file_id: Optional[int],
        file_data_backup: Optional[Dict[str, Any]],
        backup_uuid: Optional[str],
        backup_manager: Optional[BackupManager],
        temp_file: Path,
        commit_message: Optional[str],
    ) -> SuccessResult | ErrorResult:
        """
        Apply changes to file and database within transaction.

        Args:
            database: Database instance
            project_id: Project ID
            root_path: Project root path
            target_path: Target file path
            source_code: Source code to write
            file_id: Existing file ID or None
            file_data_backup: Backup of file data or None
            backup_uuid: Backup UUID or None
            backup_manager: BackupManager instance or None
            temp_file: Temporary file path
            commit_message: Optional git commit message

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            # Delete old data if file exists
            if file_id:
                self._delete_file_data(database, file_id)

            # Update file record
            file_id = self._update_file_record(
                database, project_id, root_path, target_path, source_code, file_id
            )

            # Add new data (AST, CST, entities)
            update_result = database.update_file_data_atomic(
                file_path=str(target_path),
                project_id=project_id,
                root_dir=root_path,
                source_code=source_code,
                file_id=file_id,
            )

            if not update_result.get("success"):
                raise RuntimeError(
                    f"Failed to update file data: {update_result.get('error')}"
                )

            # Atomically replace file
            os.replace(str(temp_file), str(target_path))

            # Commit transaction
            database.commit_transaction()

            # Git commit (if requested)
            git_success = False
            git_error = None
            if commit_message:
                git_success, git_error = create_git_commit(
                    root_path, target_path, commit_message
                )
                if not git_success:
                    logger.warning(f"Failed to create git commit: {git_error}")

            return SuccessResult(
                data={
                    "success": True,
                    "file_path": str(target_path),
                    "file_id": file_id,
                    "backup_uuid": backup_uuid,
                    "update_result": update_result,
                    "git_commit": {
                        "success": git_success,
                        "error": git_error,
                    },
                }
            )

        except Exception as error:
            # Rollback transaction
            try:
                database.rollback_transaction()
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {rollback_error}")

            # Handle rollback
            self._handle_rollback(
                database,
                file_id,
                file_data_backup,
                backup_uuid,
                backup_manager,
                root_path,
                target_path,
            )

            raise error

    async def execute(
        self,
        project_id: str,
        file_path: str,
        tree_id: str,
        commit_message: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute compose_cst_module command.

        Args:
            project_id: Project ID
            file_path: File path relative to project root
            tree_id: CST tree ID
            commit_message: Optional git commit message

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            # Resolve project root from database
            root_path = self._resolve_project_root(project_id=project_id, root_dir=None)

            # Get CST tree
            tree = get_tree(tree_id)
            if not tree:
                return ErrorResult(
                    message=f"Tree not found: {tree_id}",
                    code="TREE_NOT_FOUND",
                    details={"tree_id": tree_id},
                )

            # Generate source code from tree
            source_code = tree.module.code

            # Resolve target file path
            target_path = (root_path / file_path).resolve()

            if target_path.suffix != ".py":
                return ErrorResult(
                    message="Target file must be a .py file",
                    code="INVALID_FILE",
                    details={"file_path": str(target_path)},
                )

            # Step 1-2: Write to temporary file and validate
            temp_file, validation_error = self._validate_and_write_temp(
                source_code, target_path
            )
            if validation_error:
                return validation_error

            # Step 3: Get database connection
            database = self._open_database(str(root_path), auto_analyze=False)
            backup_manager = None
            backup_uuid = None
            file_data_backup = None

            try:
                # Step 4: Check if file exists in database and backup data
                file_record = None
                file_id = None

                if target_path.exists():
                    # Get file record
                    file_record = database.get_file_by_path(
                        str(target_path), project_id
                    )
                    if file_record:
                        file_id = file_record["id"]
                        # Backup file data
                        file_data_backup = self._backup_file_data(database, file_id)

                # Step 5: Create file backup
                if target_path.exists():
                    backup_manager = BackupManager(root_path)
                    backup_uuid = backup_manager.create_backup(
                        target_path,
                        command="compose_cst_module",
                        comment=commit_message or "",
                    )

                # Step 6: Begin database transaction
                database.begin_transaction()

                try:
                    # Step 7-12: Apply changes
                    result = self._apply_changes(
                        database=database,
                        project_id=project_id,
                        root_path=root_path,
                        target_path=target_path,
                        source_code=source_code,
                        file_id=file_id,
                        file_data_backup=file_data_backup,
                        backup_uuid=backup_uuid,
                        backup_manager=backup_manager,
                        temp_file=temp_file,
                        commit_message=commit_message,
                    )
                    temp_file = None  # File was moved, don't delete it
                    return result

                except Exception as error:
                    # Rollback handled in _apply_changes
                    raise error

            finally:
                database.disconnect()

                # Clean up temporary file if it still exists
                if temp_file and temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception as cleanup_error:
                        logger.warning(
                            f"Failed to delete temporary file: {cleanup_error}"
                        )

        except Exception as e:
            return self._handle_error(e, "CST_COMPOSE_ERROR", "compose_cst_module")
