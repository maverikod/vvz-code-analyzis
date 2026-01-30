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
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.backup_manager import BackupManager
from ..core.git_integration import create_git_commit
from ..core.cst_tree.tree_builder import get_tree

logger = logging.getLogger(__name__)


class ComposeCSTModuleCommand(BaseMCPCommand):
    """
    Compose/patch a module using CST tree.

    Attaches a branch (tree_id) to a node in a file or overwrites/creates a file.

    Process:
    1. Check project exists
    2. Get CST tree (branch) from tree_id and check it's not empty
    3. If node_id is specified → load file, find node, insert branch code into node
    4. If node_id is empty → overwrite file with branch (or create new file)
    5. Write to temporary file
    6. Validate temporary file (compile, flake8, mypy, docstrings)
    7. If validation fails, return errors
    8. Check if file exists in database, backup data if exists
    9. Begin database transaction
    10. Delete all old data (clear_file_data)
    11. Add new data (update_file_data_atomic)
    12. Atomically replace file
    13. Commit transaction
    14. Git commit (if commit_message provided)
    15. On any error: rollback transaction and restore data from backup

    Validations:
    - Project existence
    - Node existence (if node_id provided)
    - Branch is not empty
    - Compilation (syntax check)
    - Flake8 (linting)
    - MyPy (type checking)
    - Docstrings:
      * File-level docstring
      * Class docstrings
      * Method docstrings
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
                    "description": "CST tree ID from cst_load_file command (branch to attach)",
                },
                "node_id": {
                    "type": "string",
                    "description": "Node ID to attach branch to (optional). If empty - file will be overwritten with branch. If specified - branch will be inserted after the node.",
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
        # Get file record using select
        file_rows = database.select("files", where={"id": file_id}, limit=1)
        if not file_rows:
            return None
        file_record = file_rows[0]

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

        # Handle different result formats
        def extract_data(result):
            """Extract data from database.execute result."""
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return result.get("data", [])
            else:
                return []

        backup_data = {
            "file_record": file_record,
            "classes": extract_data(classes_result),
            "functions": extract_data(functions_result),
            "imports": extract_data(imports_result),
            "usages": extract_data(usages_result),
            "issues": extract_data(issues_result),
            "code_content": extract_data(code_content_result),
            "ast_trees": extract_data(ast_trees_result),
            "cst_trees": extract_data(cst_trees_result),
        }

        # Get methods for all classes
        class_ids = [row["id"] for row in backup_data["classes"]]
        if class_ids:
            placeholders = ",".join("?" * len(class_ids))
            methods_result = database.execute(
                f"SELECT * FROM methods WHERE class_id IN ({placeholders})",
                tuple(class_ids),
            )
            backup_data["methods"] = extract_data(methods_result)
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
        # Handle different result formats
        if isinstance(class_result, list):
            class_data = class_result
        elif isinstance(class_result, dict):
            class_data = class_result.get("data", [])
        else:
            class_data = []
        class_ids = [row["id"] for row in class_data]
        
        content_result = database.execute(
            "SELECT id FROM code_content WHERE file_id = ?", (file_id,)
        )
        # Handle different result formats
        if isinstance(content_result, list):
            content_data = content_result
        elif isinstance(content_result, dict):
            content_data = content_result.get("data", [])
        else:
            content_data = []
        content_ids = [row["id"] for row in content_data]

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
                project_id = ?, updated_at = julianday('now')
            WHERE id = ?
            """,
            (
                file_record["path"],
                file_record["lines"],
                file_record["last_modified"],
                file_record["has_docstring"],
                file_record["project_id"],
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
    ) -> tuple[Path, ErrorResult | None, Dict[str, Any] | None]:
        """
        Write source code to temporary file and validate it with flake8 and mypy.

        Args:
            source_code: Source code to write
            target_path: Target file path

        Returns:
            Tuple of (temp_file_path, error_result or None, validation_results or None)
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
                None,
            )

        # Validate with flake8 and mypy
        from ..core.cst_module.validation import validate_file_in_temp

        validation_success, validation_error, validation_results = validate_file_in_temp(
            source_code=source_code,
            temp_file_path=temp_file,
            validate_linter=True,  # Enable flake8
            validate_type_checker=True,  # Enable mypy
        )

        if not validation_success:
            # Build detailed error message
            error_parts = []
            for validation_type, result in validation_results.items():
                if not result.success:
                    if result.error_message:
                        error_parts.append(f"{validation_type}: {result.error_message}")
                    elif result.errors:
                        error_parts.append(
                            f"{validation_type}: {len(result.errors)} error(s)"
                        )
            error_message = "; ".join(error_parts) if error_parts else "Validation failed"

            # Format validation results for details
            validation_details = {
                validation_type: {
                    "success": result.success,
                    "error_message": result.error_message,
                    "errors": result.errors[:10],  # Limit to first 10 errors
                }
                for validation_type, result in validation_results.items()
            }

            temp_file.unlink()
            return (
                temp_file,
                ErrorResult(
                    message=f"Validation failed: {error_message}",
                    code="VALIDATION_ERROR",
                    details={
                        "error": error_message,
                        "validation_results": validation_details,
                    },
                ),
                validation_results,
            )

        return (temp_file, None, validation_results)

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
        lines = source_code.count("\n") + (1 if source_code else 0)
        stripped = source_code.lstrip()
        has_docstring = stripped.startswith('"""') or stripped.startswith("'''")

        if not file_id:
            import time
            from ..core.database_client.objects.file import File
            from ..core.path_normalization import normalize_path_simple

            # Normalize path to absolute
            normalized_path = normalize_path_simple(str(target_path))

            # Create File object
            file_obj = File(
                project_id=project_id,
                path=normalized_path,
                lines=lines,
                last_modified=time.time(),
                has_docstring=has_docstring,
            )
            
            # Create file in database
            created_file = database.create_file(file_obj)
            file_id = created_file.id
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
            transaction_id = None
            try:
                transaction_id = database.begin_transaction()
                self._restore_file_data(database, file_id, file_data_backup)
                database.commit_transaction(transaction_id)
                logger.info(f"File data restored from backup for file_id={file_id}")
            except Exception as restore_error:
                logger.error(
                    f"Failed to restore file data: {restore_error}",
                    exc_info=True,
                )
                if transaction_id:
                    try:
                        database.rollback_transaction(transaction_id)
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

    def _update_file_data_atomic(
        self,
        database,
        file_id: int,
        project_id: str,
        source_code: str,
        file_path: str,
    ) -> Dict[str, Any]:
        """
        Atomically update all file data (AST, CST, entities) using DatabaseClient.

        Args:
            database: DatabaseClient instance
            file_id: File ID
            project_id: Project ID
            source_code: Source code to parse
            file_path: File path

        Returns:
            Dictionary with update result
        """
        import ast
        import hashlib
        import json
        import time

        try:
            # Parse AST from source_code
            try:
                tree = ast.parse(source_code, filename=file_path)
            except SyntaxError as e:
                logger.warning(f"Syntax error in {file_path}: {e}")
                return {
                    "success": False,
                    "error": f"Syntax error: {e}",
                    "file_path": file_path,
                    "file_id": file_id,
                }
            except Exception as e:
                logger.error(f"Error parsing AST for {file_path}: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": f"Failed to parse AST: {e}",
                    "file_path": file_path,
                    "file_id": file_id,
                }

            # Calculate file metadata
            file_mtime = time.time()

            # Save AST tree
            ast_dump = ast.dump(tree)  # Returns list/dict structure
            ast_data = ast_dump if isinstance(ast_dump, dict) else {"ast": ast_dump}
            try:
                database.save_ast(file_id, ast_data)
                ast_updated = True
            except Exception as e:
                logger.error(f"Error saving AST for {file_path}: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": f"Failed to save AST: {e}",
                    "file_path": file_path,
                    "file_id": file_id,
                }

            # Save CST tree (source code)
            try:
                database.save_cst(file_id, source_code)
                cst_updated = True
            except Exception as e:
                logger.error(f"Error saving CST for {file_path}: {e}", exc_info=True)
                return {
                    "success": False,
                    "error": f"Failed to save CST: {e}",
                    "file_path": file_path,
                    "file_id": file_id,
                }

            # Extract and save entities
            from ..core.database_client.objects.class_function import Class, Function
            from ..core.database_client.objects.method_import import Method, Import

            classes_added = 0
            functions_added = 0
            methods_added = 0
            imports_added = 0

            class_nodes: Dict[ast.ClassDef, int] = {}

            # Extract classes and methods
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    docstring = ast.get_docstring(node)
                    bases: List[str] = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            bases.append(base.id)
                        else:
                            try:
                                bases.append(ast.unparse(base))
                            except AttributeError:
                                bases.append(str(base))

                    # Create Class object
                    class_obj = Class(
                        file_id=file_id,
                        name=node.name,
                        line=node.lineno,
                        docstring=docstring,
                        bases=bases,
                    )
                    try:
                        created_class = database.create_class(class_obj)
                        classes_added += 1
                        class_nodes[node] = created_class.id

                        # Extract methods from class
                        for item in node.body:
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                method_docstring = ast.get_docstring(item)
                                method_args = []
                                if item.args:
                                    for arg in item.args.args:
                                        arg_name = arg.arg
                                        if arg.annotation:
                                            try:
                                                arg_name += f": {ast.unparse(arg.annotation)}"
                                            except AttributeError:
                                                arg_name += f": {str(arg.annotation)}"
                                        method_args.append(arg_name)

                                # Create Method object
                                method_obj = Method(
                                    class_id=created_class.id,
                                    name=item.name,
                                    line=item.lineno,
                                    docstring=method_docstring,
                                    args=method_args,
                                )
                                try:
                                    database.create_method(method_obj)
                                    methods_added += 1
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to create method {item.name}: {e}",
                                        exc_info=True,
                                    )
                    except Exception as e:
                        logger.warning(
                            f"Failed to create class {node.name}: {e}", exc_info=True
                        )

            # Extract top-level functions
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Check if it's a method (inside a class)
                    is_method = False
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef):
                            if any(
                                node == item
                                for item in parent.body
                                if isinstance(
                                    item, (ast.FunctionDef, ast.AsyncFunctionDef)
                                )
                            ):
                                is_method = True
                                break

                    if not is_method:
                        docstring = ast.get_docstring(node)
                        args = []
                        if node.args:
                            for arg in node.args.args:
                                arg_name = arg.arg
                                if arg.annotation:
                                    try:
                                        arg_name += f": {ast.unparse(arg.annotation)}"
                                    except AttributeError:
                                        arg_name += f": {str(arg.annotation)}"
                                args.append(arg_name)

                        # Create Function object
                        function_obj = Function(
                            file_id=file_id,
                            name=node.name,
                            line=node.lineno,
                            docstring=docstring,
                            args=args,
                        )
                        try:
                            database.create_function(function_obj)
                            functions_added += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to create function {node.name}: {e}",
                                exc_info=True,
                            )

            # Extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        import_obj = Import(
                            file_id=file_id,
                            module="",
                            name=alias.name,
                            import_type="import",
                            line=node.lineno,
                        )
                        try:
                            database.create_import(import_obj)
                            imports_added += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to create import {alias.name}: {e}",
                                exc_info=True,
                            )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        import_obj = Import(
                            file_id=file_id,
                            module=module,
                            name=alias.name,
                            import_type="from",
                            line=node.lineno,
                        )
                        try:
                            database.create_import(import_obj)
                            imports_added += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to create import {alias.name}: {e}",
                                exc_info=True,
                            )

            entities_count = classes_added + functions_added + methods_added

            return {
                "success": True,
                "file_id": file_id,
                "file_path": file_path,
                "ast_updated": ast_updated,
                "cst_updated": cst_updated,
                "entities_updated": entities_count,
                "classes": classes_added,
                "functions": functions_added,
                "methods": methods_added,
                "imports": imports_added,
            }

        except Exception as e:
            logger.error(
                f"Unexpected error in _update_file_data_atomic for {file_path}: {e}",
                exc_info=True,
            )
            return {
                "success": False,
                "error": str(e),
                "file_path": file_path,
                "file_id": file_id,
            }

    def _apply_changes(
        self,
        database,
        transaction_id: str,
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
            transaction_id: Transaction ID from begin_transaction()
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
            update_result = self._update_file_data_atomic(
                database=database,
                file_id=file_id,
                project_id=project_id,
                source_code=source_code,
                file_path=str(target_path),
            )
            
            if not update_result.get("success"):
                raise RuntimeError(
                    f"Failed to update file data: {update_result.get('error')}"
                )

            # Atomically replace file
            os.replace(str(temp_file), str(target_path))

            # Commit transaction
            database.commit_transaction(transaction_id)

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
                database.rollback_transaction(transaction_id)
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
        node_id: Optional[str] = None,
        commit_message: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        """
        Execute compose_cst_module command.

        Args:
            project_id: Project ID
            file_path: File path relative to project root
            tree_id: CST tree ID (branch to attach)
            node_id: Node ID to attach branch to (optional)
            commit_message: Optional git commit message

        Returns:
            SuccessResult or ErrorResult
        """
        try:
            # Step 1: Check project exists
            root_path = self._resolve_project_root(project_id=project_id, root_dir=None)
            database = self._open_database(str(root_path), auto_analyze=False)
            try:
                project = database.get_project(project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project not found: {project_id}",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )
            finally:
                database.disconnect()

            # Step 2: Get CST tree (branch) and check it's not empty
            # If file is new and tree_id points to a different file,
            # we need to create a new tree from the branch code
            tree = get_tree(tree_id)
            if not tree:
                return ErrorResult(
                    message=f"Tree not found: {tree_id}",
                    code="TREE_NOT_FOUND",
                    details={"tree_id": tree_id},
                )

            # Check branch is not empty
            branch_code = tree.module.code.strip()
            if not branch_code:
                return ErrorResult(
                    message="Branch (tree_id) must not be empty",
                    code="EMPTY_BRANCH",
                    details={"tree_id": tree_id},
                )
            
            # If file is new, update tree's file_path to target file
            # This ensures the tree is associated with the correct file
            target_path = (root_path / file_path).resolve()
            if not target_path.exists():
                # Update tree file_path for new file
                tree.file_path = str(target_path.resolve())

            # Resolve target file path (already resolved above if file is new)
            if not 'target_path' in locals():
                target_path = (root_path / file_path).resolve()

            if target_path.suffix != ".py":
                return ErrorResult(
                    message="Target file must be a .py file",
                    code="INVALID_FILE",
                    details={"file_path": str(target_path)},
                )

            # Step 3: Determine operation mode
            file_exists = target_path.exists()

            # Step 4: Generate source code
            if node_id:
                # Mode: Attach branch to node
                if not file_exists:
                    return ErrorResult(
                        message="File does not exist. Cannot attach branch to node in non-existent file.",
                        code="FILE_NOT_FOUND",
                        details={
                            "file_path": str(target_path),
                            "node_id": node_id,
                        },
                    )

                # Load file into tree
                from ..core.cst_tree.tree_builder import load_file_to_tree

                file_tree = load_file_to_tree(str(target_path))
                file_tree_id = file_tree.tree_id

                # Check node exists
                from ..core.cst_tree.tree_metadata import get_node_metadata

                node_metadata = get_node_metadata(file_tree_id, node_id)
                if not node_metadata:
                    return ErrorResult(
                        message=f"Node not found: {node_id}",
                        code="NODE_NOT_FOUND",
                        details={"node_id": node_id, "file_path": str(target_path)},
                    )

                # Insert branch code into node
                from ..core.cst_tree.tree_modifier import modify_tree
                from ..core.cst_tree.models import TreeOperation, TreeOperationType

                # Insert branch code after the target node
                operations = [
                    TreeOperation(
                        action=TreeOperationType.INSERT,
                        target_node_id=node_id,
                        code=branch_code,
                        position="after",
                    )
                ]

                # Apply modification
                modified_tree = modify_tree(file_tree_id, operations)
                source_code = modified_tree.module.code
            else:
                # Mode: Overwrite file with branch (or create new file)
                # If file is new, use branch code directly (tree is already loaded)
                # The branch tree_id contains the code we want to write
                source_code = branch_code

            # Step 5: Write to temporary file and validate with flake8 and mypy
            temp_file, validation_error, validation_results = self._validate_and_write_temp(
                source_code, target_path
            )
            if validation_error:
                return validation_error

            # Step 6: Get database connection
            database = self._open_database(str(root_path), auto_analyze=False)
            backup_manager = None
            backup_uuid = None
            file_data_backup = None

            try:
                # Step 7: Check if file exists in database and backup data
                file_record = None
                file_id = None

                if file_exists:
                    # Normalize path to absolute for database lookup
                    from ..core.path_normalization import normalize_path_simple

                    normalized_path = normalize_path_simple(str(target_path))
                    
                    # Get file record using select
                    file_rows = database.select(
                        "files",
                        where={"path": normalized_path, "project_id": project_id},
                        limit=1,
                    )
                    if file_rows:
                        file_record = file_rows[0]
                        file_id = file_record["id"]
                        # Backup file data
                        file_data_backup = self._backup_file_data(database, file_id)

                # Step 8: Create file backup
                if file_exists:
                    backup_manager = BackupManager(root_path)
                    backup_uuid = backup_manager.create_backup(
                        target_path,
                        command="compose_cst_module",
                        comment=commit_message or "",
                    )

                # Step 9: Begin database transaction
                transaction_id = database.begin_transaction()

                try:
                    # Step 10-15: Apply changes
                    result = self._apply_changes(
                        database=database,
                        transaction_id=transaction_id,
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
                    
                    # Add validation results to response
                    if validation_results and isinstance(result, SuccessResult):
                        if result.data:
                            result.data["validation_results"] = {
                                validation_type: {
                                    "success": val_result.success,
                                    "error_message": val_result.error_message,
                                    "errors_count": len(val_result.errors),
                                }
                                for validation_type, val_result in validation_results.items()
                            }
                    
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
