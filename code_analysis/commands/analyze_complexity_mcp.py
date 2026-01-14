"""
MCP command wrapper: analyze_complexity.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.complexity_analyzer import analyze_file_complexity
from .base_mcp_command import BaseMCPCommand


class AnalyzeComplexityMCPCommand(BaseMCPCommand):
    """Analyze cyclomatic complexity for functions and methods."""

    name = "analyze_complexity"
    version = "1.0.0"
    descr = "Analyze cyclomatic complexity for functions and methods in a project"
    category = "analysis"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters.

        Returns:
            JSON schema for command parameters.
        """
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "description": (
                "Analyze cyclomatic complexity for functions and methods. "
                "Complexity measures the number of linearly independent paths "
                "through code. Higher complexity indicates code that may need refactoring."
            ),
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": "Optional path to specific file to analyze (absolute or relative to root_dir)",
                },
                "min_complexity": {
                    "type": "integer",
                    "description": "Optional minimum complexity threshold for filtering results",
                    "default": 1,
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
        min_complexity: int = 1,
        **kwargs,
    ) -> SuccessResult:
        """Execute complexity analysis.

        Args:
            root_dir: Project root directory.
            file_path: Optional path to specific file to analyze.
            project_id: Optional project UUID.
            min_complexity: Minimum complexity threshold for filtering.

        Returns:
            SuccessResult with complexity analysis data.
        """
        try:
            root_path = self._validate_root_dir(root_dir)
            db = self._open_database(root_dir)
            proj_id = self._get_project_id(db, root_path, project_id)

            if not proj_id:
                db.disconnect()
                return ErrorResult(
                    message="Project not found", code="PROJECT_NOT_FOUND"
                )

            results: List[Dict[str, Any]] = []

            if file_path:
                # Analyze specific file
                file_path_obj = self._validate_file_path(file_path, root_path)
                analysis = analyze_file_complexity(str(file_path_obj))

                # Filter by min_complexity and format results
                for func in analysis["functions"]:
                    if func["complexity"] >= min_complexity:
                        results.append(
                            {
                                "file_path": str(file_path_obj.relative_to(root_path)),
                                "function_name": func["name"],
                                "complexity": func["complexity"],
                                "line": func["line"],
                                "type": "function",
                            }
                        )

                for method in analysis["methods"]:
                    if method["complexity"] >= min_complexity:
                        results.append(
                            {
                                "file_path": str(file_path_obj.relative_to(root_path)),
                                "function_name": method["name"],
                                "complexity": method["complexity"],
                                "line": method["line"],
                                "type": "method",
                                "class_name": method.get("class_name"),
                            }
                        )
            else:
                # Analyze all files in project
                result = db.execute(
                    "SELECT id, path FROM files WHERE project_id = ? AND deleted = 0",
                    (proj_id,),
                )
                files = result.get("data", [])

                for file_record in files:
                    file_path_str = file_record["path"]

                    # Resolve full path
                    if Path(file_path_str).is_absolute():
                        full_path = Path(file_path_str)
                    else:
                        full_path = root_path / file_path_str

                    if not full_path.exists() or not full_path.is_file():
                        continue

                    try:
                        analysis = analyze_file_complexity(str(full_path))

                        # Filter by min_complexity and format results
                        for func in analysis["functions"]:
                            if func["complexity"] >= min_complexity:
                                results.append(
                                    {
                                        "file_path": file_path_str,
                                        "function_name": func["name"],
                                        "complexity": func["complexity"],
                                        "line": func["line"],
                                        "type": "function",
                                    }
                                )

                        for method in analysis["methods"]:
                            if method["complexity"] >= min_complexity:
                                results.append(
                                    {
                                        "file_path": file_path_str,
                                        "function_name": method["name"],
                                        "complexity": method["complexity"],
                                        "line": method["line"],
                                        "type": "method",
                                        "class_name": method.get("class_name"),
                                    }
                                )
                    except SyntaxError:
                        # Skip files with syntax errors
                        continue
                    except Exception:
                        # Skip files that can't be analyzed
                        continue

            db.disconnect()

            # Sort by complexity (descending)
            results.sort(key=lambda x: x["complexity"], reverse=True)

            return SuccessResult(
                data={
                    "results": results,
                    "total_count": len(results),
                    "min_complexity": min_complexity,
                }
            )
        except Exception as e:
            return self._handle_error(
                e, "ANALYZE_COMPLEXITY_ERROR", "analyze_complexity"
            )

    @classmethod
    def metadata(cls: type["AnalyzeComplexityMCPCommand"]) -> Dict[str, Any]:
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
                "The analyze_complexity command analyzes cyclomatic complexity for functions and methods "
                "in a project. Cyclomatic complexity measures the number of linearly independent paths "
                "through code, helping identify functions that may need refactoring.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. If file_path provided:\n"
                "   - Analyzes specific file using AST parsing\n"
                "   - Calculates complexity for each function and method\n"
                "   - Filters results by min_complexity threshold\n"
                "5. If file_path not provided:\n"
                "   - Retrieves all files from database\n"
                "   - Analyzes each file (skips syntax errors)\n"
                "   - Calculates complexity for all functions and methods\n"
                "   - Filters results by min_complexity threshold\n"
                "6. Sorts results by complexity (descending)\n"
                "7. Returns list of functions/methods with complexity scores\n\n"
                "Complexity Calculation:\n"
                "- Uses AST analysis to count decision points (if, for, while, except, etc.)\n"
                "- Complexity = 1 + number of decision points\n"
                "- Higher complexity indicates more complex code paths\n"
                "- Common thresholds: 1-10 (simple), 11-20 (moderate), 21+ (complex)\n\n"
                "Use cases:\n"
                "- Identify complex functions that need refactoring\n"
                "- Find methods with high complexity scores\n"
                "- Monitor code complexity over time\n"
                "- Focus refactoring efforts on most complex code\n\n"
                "Important notes:\n"
                "- Skips files with syntax errors (continues with other files)\n"
                "- Results sorted by complexity (highest first)\n"
                "- min_complexity filter helps focus on problematic code\n"
                "- Complexity is calculated for both functions and methods"
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
                "file_path": {
                    "description": (
                        "Optional path to specific file to analyze. Can be absolute or relative to root_dir. "
                        "If provided, only analyzes this file. If omitted, analyzes all files in project."
                    ),
                    "type": "string",
                    "required": False,
                },
                "min_complexity": {
                    "description": (
                        "Minimum complexity threshold for filtering results. Default is 1. "
                        "Only functions/methods with complexity >= min_complexity are returned. "
                        "Use higher values (e.g., 10, 20) to focus on complex code."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 1,
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
                    "description": "Analyze complexity for specific file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Analyzes cyclomatic complexity for all functions and methods in src/main.py."
                    ),
                },
                {
                    "description": "Find complex functions (complexity >= 10)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "min_complexity": 10,
                    },
                    "explanation": (
                        "Finds all functions and methods with complexity >= 10 across the project. "
                        "Useful for identifying code that needs refactoring."
                    ),
                },
                {
                    "description": "Find very complex code (complexity >= 20)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "min_complexity": 20,
                    },
                    "explanation": (
                        "Finds functions and methods with very high complexity (>= 20). "
                        "These are prime candidates for refactoring."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "ANALYZE_COMPLEXITY_ERROR": {
                    "description": "General error during complexity analysis",
                    "example": "Database error, file access error, or analysis failure",
                    "solution": (
                        "Check database integrity, verify file paths, ensure files are readable. "
                        "Syntax errors in files are skipped automatically."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "results": (
                            "List of complexity results. Each entry contains:\n"
                            "- file_path: File where function/method is defined\n"
                            "- function_name: Name of function or method\n"
                            "- complexity: Cyclomatic complexity score (integer)\n"
                            "- line: Line number where function/method is defined\n"
                            "- type: 'function' or 'method'\n"
                            "- class_name: Class name (for methods only)"
                        ),
                        "total_count": "Total number of results found",
                        "min_complexity": "Minimum complexity threshold used",
                    },
                    "example": {
                        "results": [
                            {
                                "file_path": "src/main.py",
                                "function_name": "process_data",
                                "complexity": 15,
                                "line": 42,
                                "type": "function",
                            },
                            {
                                "file_path": "src/handlers.py",
                                "function_name": "execute",
                                "complexity": 12,
                                "line": 20,
                                "type": "method",
                                "class_name": "TaskHandler",
                            },
                        ],
                        "total_count": 2,
                        "min_complexity": 1,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, ANALYZE_COMPLEXITY_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use min_complexity parameter to focus on problematic code",
                "Start with min_complexity=10 to find moderately complex code",
                "Use min_complexity=20+ to find very complex code requiring immediate attention",
                "Analyze specific files first before running project-wide analysis",
                "Review results sorted by complexity (highest first) to prioritize refactoring",
                "Combine with comprehensive_analysis for complete code quality overview",
            ],
        }
