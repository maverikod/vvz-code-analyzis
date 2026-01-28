"""
MCP command: cst_create_file

Create a new Python file with docstring and return tree_id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_builder import create_tree_from_code
from ..core.cst_tree.tree_saver import save_tree_to_file

logger = logging.getLogger(__name__)


class CSTCreateFileCommand(BaseMCPCommand):
    """Create a new Python file with docstring."""

    name = "cst_create_file"
    version = "1.0.0"
    descr = "Create a new Python file with docstring and return tree_id"
    category = "cst"
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
                    "description": "Target Python file path (relative to project root)",
                },
                "docstring": {
                    "type": "string",
                    "description": "File-level docstring (required). Will be formatted as triple-quoted string.",
                },
                "root_dir": {
                    "type": "string",
                    "description": "Server root directory (optional, for database access)",
                },
            },
            "required": ["project_id", "file_path", "docstring"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        docstring: str,
        root_dir: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        """
        Create a new Python file with docstring.

        Process:
        1. Validate project exists
        2. Resolve absolute file path
        3. Check file doesn't exist
        4. Format docstring as triple-quoted string
        5. Create CST tree from docstring code
        6. Save tree to file (creates file on disk and in database)
        7. Return tree_id

        Args:
            project_id: Project ID
            file_path: File path relative to project root
            docstring: File-level docstring
            root_dir: Optional server root directory

        Returns:
            SuccessResult with tree_id and file_path
        """
        try:
            # Resolve server root_dir for database access
            if not root_dir:
                from ..core.storage_paths import (
                    load_raw_config,
                    resolve_storage_paths,
                )

                config_path = self._resolve_config_path()
                config_data = load_raw_config(config_path)
                storage = resolve_storage_paths(
                    config_data=config_data, config_path=config_path
                )
                root_dir = str(storage.config_dir.parent) if hasattr(storage, 'config_dir') else "/"

            # Open database
            database = self._open_database(root_dir, auto_analyze=False)
            try:
                # Resolve absolute path using project_id and watch_dir/project_name
                target = self._resolve_file_path_from_project(
                    database, project_id, file_path
                )

                if target.suffix != ".py":
                    return ErrorResult(
                        message="Target file must be a .py file",
                        code="INVALID_FILE",
                        details={"file_path": str(target)},
                    )

                # Check file doesn't exist
                if target.exists():
                    return ErrorResult(
                        message=f"File already exists: {target}",
                        code="FILE_EXISTS",
                        details={"file_path": str(target)},
                    )

                # Get project root from project
                project = database.get_project(project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project {project_id} not found",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )

                project_root = Path(project.root_path)

                # Get or create dataset_id
                dataset_id = BaseMCPCommand._get_or_create_dataset(
                    database, project_id, str(project_root)
                )

                # Format docstring as triple-quoted string
                docstring_value = docstring.strip()
                if not (
                    docstring_value.startswith('"""') or docstring_value.startswith("'''")
                ):
                    docstring_value = f'"""{docstring_value}"""'

                # Create source code with docstring
                source_code = docstring_value

                # Create CST tree from code
                tree = create_tree_from_code(
                    file_path=str(target),
                    source_code=source_code,
                )

                # Save tree to file (creates file on disk and in database)
                result = save_tree_to_file(
                    tree_id=tree.tree_id,
                    file_path=str(target),
                    root_dir=project_root,
                    project_id=project_id,
                    dataset_id=dataset_id,
                    database=database,
                    validate=True,
                    backup=False,  # No backup needed for new file
                    commit_message=None,
                )

                if not result.get("success"):
                    return ErrorResult(
                        message=result.get("error", "Failed to save tree"),
                        code="CST_SAVE_ERROR",
                        details=result,
                    )

                # Convert metadata to dictionaries
                nodes = [meta.to_dict() for meta in tree.metadata_map.values()]

                data = {
                    "success": True,
                    "tree_id": tree.tree_id,
                    "file_path": str(target),
                    "nodes": nodes,
                    "total_nodes": len(nodes),
                }

                return SuccessResult(data=data)

            finally:
                database.disconnect()

        except Exception as e:
            logger.exception("cst_create_file failed: %s", e)
            return ErrorResult(
                message=f"cst_create_file failed: {e}", code="CST_CREATE_ERROR"
            )
