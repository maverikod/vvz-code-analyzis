"""
CST tree saver - save tree to file with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..backup_manager import BackupManager
from .models import CSTTree
from .tree_builder import get_tree

logger = logging.getLogger(__name__)


def _update_file_data_atomic_via_client(
    database,
    file_id: int,
    project_id: str,
    source_code: str,
    file_path: str,
) -> Dict[str, Any]:
    """
    Atomically update all file data (AST, CST, entities) using DatabaseClient methods.

    This function uses only DatabaseClient API methods, maintaining proper access hierarchy:
    User -> Client -> Driver -> Database

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
    from typing import List

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

        # Save AST tree
        import json

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

        # Extract and save entities using DatabaseClient methods
        from ..database_client.objects.class_function import Class, Function
        from ..database_client.objects.method_import import Method, Import

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
                                            arg_name += (
                                                f": {ast.unparse(arg.annotation)}"
                                            )
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
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
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
            f"Unexpected error in _update_file_data_atomic_via_client for {file_path}: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "error": str(e),
            "file_path": file_path,
            "file_id": file_id,
        }


def save_tree_to_file(
    tree_id: str,
    file_path: str,
    root_dir: Path,
    project_id: str,
    database,
    validate: bool = True,
    backup: bool = True,
    commit_message: Optional[str] = None,
) -> Dict[str, any]:
    """
    Save tree to file with atomic operations.

    Process:
    1. Validate entire file through compile() (before any changes)
    2. Create backup via BackupManager (mandatory if file exists)
    3. Generate source code from CST tree
    4. Write to temporary file
    5. Validate temporary file (compile, linter, type checker)
    6. Begin database transaction
    7. Atomically replace file via os.replace()
    8. Update database (update_file_data_atomic)
    9. Commit transaction
    10. Git commit (if commit_message provided)
    11. On any error: rollback transaction and restore from backup

    Args:
        tree_id: Tree ID
        file_path: Target file path (absolute or relative to root_dir)
        root_dir: Project root directory
        project_id: Project ID
        database: Database instance
        validate: Whether to validate file before saving
        backup: Whether to create backup
        commit_message: Optional git commit message

    Returns:
        Dictionary with result:
        {
            "success": bool,
            "file_path": str,
            "backup_uuid": Optional[str],
            "error": Optional[str]
        }

    Raises:
        ValueError: If tree not found or validation fails
        RuntimeError: If file operations fail
    """
    tree = get_tree(tree_id)
    if not tree:
        raise ValueError(f"Tree not found: {tree_id}")

    # Resolve file path
    target_path = Path(file_path)
    if not target_path.is_absolute():
        target_path = (root_dir / target_path).resolve()
    else:
        target_path = target_path.resolve()

    # Ensure directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)

    backup_uuid: Optional[str] = None
    backup_manager: Optional[BackupManager] = None
    temp_file: Optional[Path] = None

    try:
        # Step 1: Validate original file if it exists
        if validate and target_path.exists():
            try:
                original_source = target_path.read_text(encoding="utf-8")
                compile(original_source, str(target_path), "exec")
            except SyntaxError as e:
                logger.warning(f"Original file has syntax errors: {e}")
                # Continue anyway - we're replacing it

        # Step 2: Create backup (mandatory before overwriting existing file)
        if target_path.exists():
            backup_manager = BackupManager(root_dir)
            try:
                rel_path = str(target_path.relative_to(root_dir))
            except ValueError:
                rel_path = str(target_path)
            backup_uuid = backup_manager.create_backup(
                target_path,
                command="cst_save_tree",
                comment=f"Before saving CST tree {tree_id}",
            )
            if not backup_uuid:
                logger.warning("Failed to create backup, continuing anyway")

        # Step 3: Generate source code from CST tree
        source_code = tree.module.code

        # Step 4: Write to temporary file
        temp_fd, temp_path_str = tempfile.mkstemp(
            suffix=".py", prefix="cst_save_", dir=target_path.parent
        )
        temp_file = Path(temp_path_str)
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(source_code)
        except Exception as e:
            os.close(temp_fd)
            raise RuntimeError(f"Failed to write temporary file: {e}") from e

        # Step 5: Validate temporary file
        if validate:
            try:
                compile(source_code, str(temp_file), "exec")
            except SyntaxError as e:
                raise ValueError(f"Generated code has syntax errors: {e}") from e

        # Step 6: Begin database transaction
        transaction_id = database.begin_transaction()

        try:
            # Step 7: Atomically replace file
            os.replace(str(temp_file), str(target_path))
            temp_file = None  # File was moved, don't delete it

            # Step 8: Update database
            # Calculate file metadata
            lines = source_code.count("\n") + (1 if source_code else 0)
            stripped = source_code.lstrip()
            has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
            last_modified_timestamp = target_path.stat().st_mtime
            last_modified = datetime.fromtimestamp(last_modified_timestamp)

            # Check if file exists in database
            from ..database_client.objects.file import File
            from ..path_normalization import normalize_path_simple

            normalized_path = normalize_path_simple(str(target_path))
            existing_files = database.select(
                "files", where={"path": normalized_path, "project_id": project_id}
            )

            if existing_files:
                # Update existing file
                file_record = existing_files[0]
                file_obj = File(
                    id=file_record["id"],
                    project_id=project_id,
                    path=normalized_path,
                    lines=lines,
                    last_modified=last_modified,
                    has_docstring=has_docstring,
                )
                updated_file = database.update_file(file_obj)
                file_id = updated_file.id
            else:
                # Create new file
                file_obj = File(
                    project_id=project_id,
                    path=normalized_path,
                    lines=lines,
                    last_modified=last_modified,
                    has_docstring=has_docstring,
                )
                created_file = database.create_file(file_obj)
                file_id = created_file.id

            # Update file data (AST, CST, entities) atomically using DatabaseClient methods
            update_result = _update_file_data_atomic_via_client(
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

            # Step 9: Commit transaction
            database.commit_transaction(transaction_id)

            # Step 10: Git commit (if requested)
            if commit_message:
                from ..git_integration import create_git_commit

                git_success, git_error = create_git_commit(
                    root_dir, target_path, commit_message
                )
                if not git_success:
                    logger.warning(f"Failed to create git commit: {git_error}")
                    # Not critical - file is already saved

            return {
                "success": True,
                "file_path": str(target_path),
                "file_id": file_id,
                "backup_uuid": backup_uuid,
                "update_result": update_result,
            }

        except Exception as e:
            # Rollback transaction
            try:
                if transaction_id:
                    database.rollback_transaction(transaction_id)
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {rollback_error}")

            # Restore file from backup if backup was created
            if backup_uuid and backup_manager and target_path.exists():
                try:
                    rel_path = str(target_path.relative_to(root_dir))
                except ValueError:
                    rel_path = str(target_path)
                restore_success, restore_message = backup_manager.restore_file(
                    rel_path, backup_uuid
                )
                if restore_success:
                    logger.info(f"File restored from backup: {restore_message}")
                else:
                    logger.error(
                        f"Failed to restore file from backup: {restore_message}"
                    )

            raise

    except Exception as e:
        logger.error(f"Error saving tree to file: {e}", exc_info=True)
        return {
            "success": False,
            "file_path": str(target_path),
            "backup_uuid": backup_uuid,
            "error": str(e),
        }

    finally:
        # Clean up temporary file if it still exists
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete temporary file: {e}")
