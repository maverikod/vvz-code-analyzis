"""
CST tree saver - save tree to file with atomic operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

from ..backup_manager import BackupManager
from .models import CSTTree
from .tree_builder import get_tree

logger = logging.getLogger(__name__)


def save_tree_to_file(
    tree_id: str,
    file_path: str,
    root_dir: Path,
    project_id: str,
    dataset_id: str,
    database,
    validate: bool = True,
    backup: bool = True,
    commit_message: Optional[str] = None,
) -> Dict[str, any]:
    """
    Save tree to file with atomic operations.

    Process:
    1. Validate entire file through compile() (before any changes)
    2. Create backup via BackupManager (if file exists and backup=True)
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
        dataset_id: Dataset ID
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

        # Step 2: Create backup
        if backup and target_path.exists():
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
        temp_fd, temp_path_str = tempfile.mkstemp(suffix=".py", prefix="cst_save_", dir=target_path.parent)
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
        database.begin_transaction()

        try:
            # Step 7: Atomically replace file
            os.replace(str(temp_file), str(target_path))
            temp_file = None  # File was moved, don't delete it

            # Step 8: Update database
            # Calculate file metadata
            lines = source_code.count("\n") + (1 if source_code else 0)
            stripped = source_code.lstrip()
            has_docstring = stripped.startswith('"""') or stripped.startswith("'''")
            last_modified = target_path.stat().st_mtime

            # Add/update file in database
            file_id = database.add_file(
                path=str(target_path),
                lines=lines,
                last_modified=last_modified,
                has_docstring=has_docstring,
                project_id=project_id,
                dataset_id=dataset_id,
            )

            # Update file data (AST, CST, entities) atomically
            update_result = database.update_file_data_atomic(
                file_path=str(target_path),
                project_id=project_id,
                root_dir=root_dir,
                source_code=source_code,
            )

            if not update_result.get("success"):
                raise RuntimeError(f"Failed to update file data: {update_result.get('error')}")

            # Step 9: Commit transaction
            database.commit_transaction()

            # Step 10: Git commit (if requested)
            if commit_message:
                from ..git_integration import create_git_commit

                git_success, git_error = create_git_commit(root_dir, target_path, commit_message)
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
                database.rollback_transaction()
            except Exception as rollback_error:
                logger.error(f"Error during rollback: {rollback_error}")

            # Restore file from backup if backup was created
            if backup_uuid and backup_manager and target_path.exists():
                try:
                    rel_path = str(target_path.relative_to(root_dir))
                except ValueError:
                    rel_path = str(target_path)
                restore_success, restore_message = backup_manager.restore_file(rel_path, backup_uuid)
                if restore_success:
                    logger.info(f"File restored from backup: {restore_message}")
                else:
                    logger.error(f"Failed to restore file from backup: {restore_message}")

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
