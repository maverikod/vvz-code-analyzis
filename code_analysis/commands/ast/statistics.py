"""
MCP command wrapper: ast_statistics.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class ASTStatisticsMCPCommand(BaseMCPCommand):
    """Get AST statistics for project or a specific file."""

    name = "ast_statistics"
    version = "1.0.0"
    descr = "Collect AST statistics for project or single file"
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {
                    "type": "string",
                    "description": "Project root directory (contains data/code_analysis.db)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to compute stats for (absolute or relative)",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project UUID; if omitted, inferred by root_dir",
                },
            },
            "required": ["root_dir"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: Optional[str] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult:
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)
            if not proj_id:
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            # Get AST statistics from database
            if file_path:
                file_record = db.get_file_by_path(file_path, proj_id)
                if not file_record:
                    db.disconnect()
                    return ErrorResult(
                        message=f"File not found: {file_path}",
                        code="FILE_NOT_FOUND",
                    )
                row = db._fetchone(
                    "SELECT COUNT(*) as count FROM ast_trees WHERE file_id = ?",
                    (file_record["id"],),
                )
                ast_count = row["count"] if row else 0
                db.disconnect()
                return SuccessResult(
                    data={
                        "success": True,
                        "file_path": file_path,
                        "ast_trees_count": ast_count,
                    }
                )
            else:
                # Project-wide stats
                row = db._fetchone(
                    "SELECT COUNT(*) as count FROM ast_trees WHERE project_id = ?",
                    (proj_id,),
                )
                ast_count = row["count"] if row else 0
                row = db._fetchone(
                    "SELECT COUNT(*) as count FROM files WHERE project_id = ? AND (deleted = 0 OR deleted IS NULL)",
                    (proj_id,),
                )
                file_count = row["count"] if row else 0
                db.disconnect()
                return SuccessResult(
                    data={
                        "success": True,
                        "project_id": proj_id,
                        "files_count": file_count,
                        "ast_trees_count": ast_count,
                    }
                )
        except Exception as e:
            return self._handle_error(e, "AST_STATS_ERROR", "ast_statistics")

    @classmethod
    def metadata(cls: type["ASTStatisticsMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "The ast_statistics command collects and returns AST (Abstract Syntax Tree) "
                "statistics for a project or a specific file. It provides counts of AST trees "
                "stored in the analysis database.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection at root_dir/data/code_analysis.db\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. If file_path provided:\n"
                "   - Finds file record in database\n"
                "   - Counts AST trees for that specific file\n"
                "   - Returns file-specific statistics\n"
                "5. If file_path not provided:\n"
                "   - Counts all AST trees for the project\n"
                "   - Counts all files in the project\n"
                "   - Returns project-wide statistics\n\n"
                "Use cases:\n"
                "- Check if AST data exists for a file before analysis\n"
                "- Get overview of project AST coverage\n"
                "- Verify AST indexing status\n"
                "- Monitor AST database size\n\n"
                "Important notes:\n"
                "- Returns count of stored AST trees, not parsed files\n"
                "- File count excludes deleted files\n"
                "- AST trees are created during file analysis/indexing\n"
                "- If file has no AST data, count will be 0"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": [
                        "/home/user/projects/my_project",
                        "./code_analysis",
                        "/var/lib/projects/project1",
                    ],
                },
                "file_path": {
                    "description": (
                        "Optional file path to get statistics for. Can be absolute or relative to root_dir. "
                        "If provided, returns statistics for that specific file only. "
                        "If omitted, returns project-wide statistics."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "code_analysis/main.py",
                        "/home/user/projects/my_project/src/module.py",
                        "src/utils/helpers.py",
                    ],
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, project_id is inferred from root_dir. "
                        "Use this parameter when working with multiple projects or when root_dir "
                        "doesn't uniquely identify the project."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    ],
                },
            },
            "usage_examples": [
                {
                    "description": "Get project-wide AST statistics",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Returns total count of files and AST trees for the entire project. "
                        "Useful for checking overall AST coverage."
                    ),
                },
                {
                    "description": "Get AST statistics for specific file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Returns AST tree count for the specific file. "
                        "Useful for verifying if a file has been analyzed."
                    ),
                },
                {
                    "description": "Get statistics with explicit project_id",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                    },
                    "explanation": (
                        "Explicitly specifies project_id. Useful when root_dir might match "
                        "multiple projects or for programmatic access."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered in database",
                    "solution": (
                        "Ensure project is registered. Run update_indexes command first "
                        "to create project entry and analyze files."
                    ),
                },
                "FILE_NOT_FOUND": {
                    "description": "File not found in database",
                    "example": "file_path='src/main.py' but file not in database",
                    "solution": (
                        "Ensure file exists and has been indexed. Check file path is correct "
                        "(absolute or relative to root_dir). Run update_indexes to index files."
                    ),
                },
                "AST_STATS_ERROR": {
                    "description": "General error during statistics collection",
                    "example": "Database error, permission denied, or corrupted database",
                    "solution": (
                        "Check database integrity, verify file permissions, ensure database "
                        "is not locked, or run repair_sqlite_database if corrupted"
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "file_path (if provided)": "File path that statistics were computed for",
                        "project_id (if file_path not provided)": "Project UUID",
                        "files_count (if file_path not provided)": "Total number of files in project",
                        "ast_trees_count": "Number of AST trees stored in database",
                        "success": "Always true on success",
                    },
                    "example_file": {
                        "success": True,
                        "file_path": "src/main.py",
                        "ast_trees_count": 1,
                    },
                    "example_project": {
                        "success": True,
                        "project_id": "928bcf10-db1c-47a3-8341-f60a6d997fe7",
                        "files_count": 42,
                        "ast_trees_count": 40,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, FILE_NOT_FOUND, AST_STATS_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use project-wide statistics to check overall AST coverage before detailed analysis",
                "Check file-specific statistics before running AST-dependent commands",
                "Run update_indexes if AST statistics show 0 counts for expected files",
                "Use explicit project_id when working with multiple projects",
                "Monitor AST tree count vs file count to detect indexing issues",
            ],
        }
