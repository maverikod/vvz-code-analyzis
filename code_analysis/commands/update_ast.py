"""
Update AST command implementation.

Allows updating AST tree for a specific file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from ..core import CodeDatabase

logger = logging.getLogger(__name__)


class UpdateASTCommand:
    """Command for updating AST tree for a file."""

    def __init__(
        self,
        database: CodeDatabase,
        project_id: str,
        file_path: str,
        force: bool = False,
    ):
        """
        Initialize update AST command.

        Args:
            database: Database instance
            project_id: Project UUID
            file_path: Path to file (relative to project root or absolute)
        """
        self.database = database
        self.project_id = project_id
        self.file_path = Path(file_path)
        self.force = force

    async def execute(self) -> Dict[str, Any]:
        """
        Execute AST update for file.

        Returns:
            Dictionary with update results
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
            # Get file modification time
            file_stat = self.file_path.stat()
            file_mtime = file_stat.st_mtime

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

            # Check if AST is outdated (unless force is True)
            if not self.force:
                if not self.database.is_ast_outdated(file_id, file_mtime):
                    return {
                        "success": True,
                        "message": f"AST tree for {self.file_path} is up to date, no update needed",
                        "file_id": file_id,
                        "skipped": True,
                    }

            # Read and parse file
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=str(self.file_path))

            # Convert AST to JSON
            ast_dict = self._ast_to_dict(tree)
            ast_json = json.dumps(ast_dict, indent=2)

            # Calculate hash
            ast_hash = hashlib.sha256(ast_json.encode("utf-8")).hexdigest()

            # Overwrite AST tree
            ast_id = await self.database.overwrite_ast_tree(
                file_id=file_id,
                project_id=self.project_id,
                ast_json=ast_json,
                ast_hash=ast_hash,
                file_mtime=file_mtime,
            )

            logger.info(f"Updated AST tree for file_id={file_id}, ast_id={ast_id}")

            return {
                "success": True,
                "message": f"AST tree updated for {self.file_path}",
                "file_id": file_id,
                "ast_id": ast_id,
                "ast_hash": ast_hash,
            }

        except SyntaxError as e:
            return {
                "success": False,
                "message": f"Syntax error in file: {e}",
                "error": str(e),
            }
        except Exception as e:
            logger.error(f"Error updating AST for {self.file_path}: {e}")
            return {
                "success": False,
                "message": f"Error updating AST: {e}",
                "error": str(e),
            }

    def _ast_to_dict(self, node: ast.AST) -> Dict[str, Any]:
        """
        Convert AST node to dictionary.

        Args:
            node: AST node

        Returns:
            Dictionary representation of AST node
        """
        if isinstance(node, ast.AST):
            result = {
                "_type": type(node).__name__,
            }
            for field, value in ast.iter_fields(node):
                if isinstance(value, list):
                    result[field] = [self._ast_to_dict(item) for item in value]
                elif isinstance(value, ast.AST):
                    result[field] = self._ast_to_dict(value)
                else:
                    result[field] = value
            return result
        elif isinstance(node, list):
            return [self._ast_to_dict(item) for item in node]
        else:
            return node

