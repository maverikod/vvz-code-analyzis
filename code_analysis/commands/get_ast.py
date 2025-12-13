"""
Command for retrieving AST tree for a file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class GetASTCommand:
    """Command for retrieving AST tree for a file."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        file_path: str,
        include_json: bool = True,
    ):
        """
        Initialize get AST command.

        Args:
            database: Database instance
            project_id: Project UUID
            file_path: Path to file (relative to project root or absolute)
            include_json: If True, include full AST JSON in response
        """
        self.database = database
        self.project_id = project_id
        self.file_path = Path(file_path)
        self.include_json = include_json

    async def execute(self) -> Dict[str, Any]:
        """
        Execute AST retrieval for file.

        Returns:
            Dictionary with AST tree data
        """
        # Resolve file path
        if not self.file_path.is_absolute():
            # Try to find file in project
            project = self.database.get_project(self.project_id)
            if not project:
                return {
                    "success": False,
                    "message": f"Project {self.project_id} not found",
                }

            project_root = Path(project["root_path"])
            self.file_path = project_root / self.file_path
        else:
            self.file_path = self.file_path.resolve()

        if not self.file_path.exists():
            return {
                "success": False,
                "message": f"File not found: {self.file_path}",
            }

        if not self.file_path.is_file():
            return {
                "success": False,
                "message": f"Path is not a file: {self.file_path}",
            }

        if not self.file_path.suffix == ".py":
            return {
                "success": False,
                "message": f"File is not a Python file: {self.file_path}",
            }

        try:
            # Get file ID from database
            file_record = self.database.get_file_by_path(
                str(self.file_path), self.project_id
            )
            if not file_record:
                return {
                    "success": False,
                    "message": f"File not found in database: {self.file_path}",
                }

            file_id = file_record["id"]

            # Get AST tree from database
            ast_record = await self.database.get_ast_tree(file_id)
            if not ast_record:
                return {
                    "success": False,
                    "message": f"AST tree not found for file: {self.file_path}",
                    "file_id": file_id,
                }

            # Prepare response
            result = {
                "success": True,
                "message": f"AST tree retrieved for {self.file_path}",
                "file_id": file_id,
                "file_path": str(self.file_path),
                "ast_id": ast_record["id"],
                "ast_hash": ast_record["ast_hash"],
                "file_mtime": ast_record["file_mtime"],
                "updated_at": ast_record["updated_at"],
            }

            # Include AST JSON if requested
            if self.include_json:
                try:
                    ast_json = ast_record["ast_json"]
                    result["ast_json"] = json.loads(ast_json) if isinstance(ast_json, str) else ast_json
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Error parsing AST JSON: {e}")
                    result["ast_json"] = None
                    result["warning"] = "Failed to parse AST JSON"

            return result

        except Exception as e:
            logger.error(f"Error retrieving AST for {self.file_path}: {e}")
            return {
                "success": False,
                "message": f"Error retrieving AST: {e}",
                "error": str(e),
            }

