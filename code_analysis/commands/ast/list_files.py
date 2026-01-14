"""
MCP command wrapper: list_project_files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand


class ListProjectFilesMCPCommand(BaseMCPCommand):
    """List all files in a project with metadata."""

    name = "list_project_files"
    version = "1.0.0"
    descr = (
        "List all files in a project with statistics (classes, functions, chunks, AST)"
    )
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
                "file_pattern": {
                    "type": "string",
                    "description": "Optional pattern to filter files (e.g., '*.py', 'core/*')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional limit on number of results",
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
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
        file_pattern: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
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

            # Get files from database
            files = db.get_project_files(proj_id, include_deleted=False)
            
            # Apply file_pattern filter if provided
            if file_pattern:
                import fnmatch
                files = [f for f in files if fnmatch.fnmatch(f["path"], file_pattern)]
            
            # Apply pagination
            total = len(files)
            if offset > 0 or limit:
                files = files[offset : offset + limit if limit else None]
            
            db.disconnect()
            
            return SuccessResult(
                data={
                    "success": True,
                    "files": files,
                    "count": len(files),
                    "total": total,
                    "offset": offset,
                }
            )
        except Exception as e:
            return self._handle_error(e, "LIST_FILES_ERROR", "list_project_files")

    @classmethod
    def metadata(cls: type["ListProjectFilesMCPCommand"]) -> Dict[str, Any]:
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
                "The list_project_files command lists all files in a project with metadata and statistics. "
                "It provides information about files including their paths, statistics (classes, functions, "
                "chunks, AST), and other metadata stored in the database.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Retrieves all project files from database (excluding deleted files)\n"
                "5. If file_pattern provided, filters files using fnmatch pattern matching\n"
                "6. Applies pagination: offset and limit\n"
                "7. Returns list of files with metadata and statistics\n\n"
                "File Metadata:\n"
                "Each file entry includes:\n"
                "- path: File path (relative to project root)\n"
                "- id: Database file ID\n"
                "- Statistics: classes count, functions count, chunks count, AST status\n"
                "- Other metadata fields from database\n\n"
                "Pattern Matching:\n"
                "- Uses fnmatch pattern matching (shell-style wildcards)\n"
                "- Examples: '*.py', 'src/*', 'tests/test_*.py'\n"
                "- Case-sensitive matching\n\n"
                "Use cases:\n"
                "- Get catalog of all files in project\n"
                "- Filter files by pattern (e.g., all Python files)\n"
                "- Get file statistics and metadata\n"
                "- Discover project structure\n"
                "- Check which files have been analyzed\n\n"
                "Important notes:\n"
                "- Excludes deleted files from results\n"
                "- Supports pagination with limit and offset\n"
                "- Pattern matching uses fnmatch (shell wildcards)\n"
                "- Returns total count before pagination"
            ),
            "parameters": {
                "root_dir": {
                    "description": (
                        "Project root directory path. Can be absolute or relative. "
                        "Must contain data/code_analysis.db file."
                    ),
                    "type": "string",
                    "required": True,
                },
                "file_pattern": {
                    "description": (
                        "Optional pattern to filter files. Uses fnmatch pattern matching "
                        "(shell-style wildcards). Examples: '*.py', 'src/*', 'tests/test_*.py'. "
                        "If not provided, returns all files."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["*.py", "src/*", "tests/test_*.py", "code_analysis/**"],
                },
                "limit": {
                    "description": (
                        "Optional limit on number of results. Use for pagination or "
                        "to limit large result sets."
                    ),
                    "type": "integer",
                    "required": False,
                },
                "offset": {
                    "description": (
                        "Offset for pagination. Default is 0. Use with limit for paginated results."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 0,
                },
                "project_id": {
                    "description": (
                        "Optional project UUID. If omitted, inferred from root_dir."
                    ),
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "List all files in project",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                    },
                    "explanation": (
                        "Returns list of all files in the project with their metadata and statistics."
                    ),
                },
                {
                    "description": "List only Python files",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_pattern": "*.py",
                    },
                    "explanation": (
                        "Returns only files matching *.py pattern (all Python files)."
                    ),
                },
                {
                    "description": "List files in specific directory",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_pattern": "src/*",
                    },
                    "explanation": (
                        "Returns only files in src/ directory."
                    ),
                },
                {
                    "description": "List files with pagination",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_pattern": "*.py",
                        "limit": 100,
                        "offset": 0,
                    },
                    "explanation": (
                        "Returns first 100 Python files. Use offset for next page."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "LIST_FILES_ERROR": {
                    "description": "General error during file listing",
                    "example": "Database error, invalid parameters, or corrupted data",
                    "solution": (
                        "Check database integrity, verify parameters, ensure project has been analyzed."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Always true on success",
                        "files": (
                            "List of file dictionaries from database. Each contains:\n"
                            "- id: Database file ID\n"
                            "- path: File path (relative to project root)\n"
                            "- Statistics: classes count, functions count, chunks count, AST status\n"
                            "- Other metadata fields from database (created_at, updated_at, etc.)"
                        ),
                        "count": "Number of files in current page (after pagination)",
                        "total": "Total number of files matching criteria (before pagination)",
                        "offset": "Offset used for pagination",
                    },
                    "example": {
                        "success": True,
                        "files": [
                            {
                                "id": 1,
                                "path": "src/main.py",
                                "classes_count": 2,
                                "functions_count": 5,
                                "chunks_count": 10,
                                "has_ast": True,
                            },
                            {
                                "id": 2,
                                "path": "src/utils.py",
                                "classes_count": 0,
                                "functions_count": 3,
                                "chunks_count": 5,
                                "has_ast": True,
                            },
                        ],
                        "count": 2,
                        "total": 42,
                        "offset": 0,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, LIST_FILES_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use file_pattern to filter files by type or location",
                "Use limit and offset for pagination with large projects",
                "Check total field to see total count before pagination",
                "Use this command to discover project structure",
                "Check file statistics to understand code distribution",
            ],
        }
