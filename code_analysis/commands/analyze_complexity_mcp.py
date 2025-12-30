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
                db.close()
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
                files = db._fetchall(
                    "SELECT id, path FROM files WHERE project_id = ? AND deleted = 0",
                    (proj_id,),
                )

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

            db.close()

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
