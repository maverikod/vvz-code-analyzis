"""
MCP command wrapper: find_duplicates.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.duplicate_detector import DuplicateDetector
from ..core.svo_client_manager import SVOClientManager
from .base_mcp_command import BaseMCPCommand

logger = logging.getLogger(__name__)


class FindDuplicatesMCPCommand(BaseMCPCommand):
    """Find duplicate code blocks in a project."""

    name = "find_duplicates"
    version = "1.0.0"
    descr = "Find duplicate code blocks using AST normalization"
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
                "Find duplicate code blocks by normalizing AST structures. "
                "This helps identify code that can be refactored to reduce duplication."
            ),
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": "Optional path to specific file to analyze (absolute or relative to root_dir)",
                },
                "min_lines": {
                    "type": "integer",
                    "description": "Minimum lines for duplicate block",
                    "default": 5,
                },
                "min_similarity": {
                    "type": "number",
                    "description": "Minimum similarity threshold (0.0-1.0)",
                    "default": 0.8,
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "use_semantic": {
                    "type": "boolean",
                    "description": "Use semantic vectors for finding logical duplicates",
                    "default": True,
                },
                "semantic_threshold": {
                    "type": "number",
                    "description": "Minimum semantic similarity threshold (0.0-1.0)",
                    "default": 0.85,
                    "minimum": 0.0,
                    "maximum": 1.0,
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
        min_lines: int = 5,
        min_similarity: float = 0.8,
        use_semantic: bool = True,
        semantic_threshold: float = 0.85,
        **kwargs,
    ) -> SuccessResult:
        """Execute duplicate detection.

        Args:
            root_dir: Project root directory.
            file_path: Optional path to specific file to analyze.
            project_id: Optional project UUID.
            min_lines: Minimum lines for duplicate block.
            min_similarity: Minimum similarity threshold for AST.
            use_semantic: Use semantic vectors for logical duplicates.
            semantic_threshold: Minimum semantic similarity threshold.

        Returns:
            SuccessResult with duplicate groups.
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

            detector = DuplicateDetector(
                min_lines=min_lines,
                min_similarity=min_similarity,
                ignore_whitespace=True,
                use_semantic=use_semantic,
                semantic_threshold=semantic_threshold,
            )

            # Initialize SVO client manager for semantic search if enabled
            svo_client_manager = None
            if use_semantic:
                try:
                    from ..core.config_manager import get_config

                    config = get_config(root_path)
                    svo_client_manager = SVOClientManager(
                        config_dict=config, root_dir=str(root_path)
                    )
                    await svo_client_manager.initialize()
                    detector.set_svo_client_manager(svo_client_manager)
                    logger.info("Semantic duplicate detection enabled")
                except Exception as e:
                    logger.warning(
                        f"Failed to initialize semantic search: {e}. "
                        "Falling back to AST-only detection."
                    )
                    detector.use_semantic = False

            all_duplicate_groups: List[Dict[str, Any]] = []

            if file_path:
                # Analyze specific file
                file_path_obj = self._validate_file_path(file_path, root_path)
                with open(file_path_obj, "r", encoding="utf-8") as f:
                    source_code = f.read()

                try:
                    import ast

                    tree = ast.parse(source_code, filename=str(file_path_obj))
                    if use_semantic and detector.use_semantic:
                        duplicates = await detector.find_duplicates_in_ast_hybrid(
                            tree, source_code
                        )
                    else:
                        duplicates = detector.find_duplicates_in_ast(tree, source_code)

                    # Add file path to occurrences
                    rel_path = str(file_path_obj.relative_to(root_path))
                    for group in duplicates:
                        for occurrence in group["occurrences"]:
                            occurrence["file_path"] = rel_path
                        all_duplicate_groups.append(group)
                except SyntaxError:
                    # Skip files with syntax errors
                    pass
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
                        with open(full_path, "r", encoding="utf-8") as f:
                            source_code = f.read()

                        import ast

                        tree = ast.parse(source_code, filename=str(full_path))
                        if use_semantic and detector.use_semantic:
                            duplicates = await detector.find_duplicates_in_ast_hybrid(
                                tree, source_code
                            )
                        else:
                            duplicates = detector.find_duplicates_in_ast(
                                tree, source_code
                            )

                        # Add file path to occurrences
                        for group in duplicates:
                            for occurrence in group["occurrences"]:
                                occurrence["file_path"] = file_path_str
                            all_duplicate_groups.append(group)
                    except SyntaxError:
                        # Skip files with syntax errors
                        continue
                    except Exception:
                        # Skip files that can't be analyzed
                        continue

            # Cleanup
            if svo_client_manager:
                try:
                    await svo_client_manager.close()
                except Exception:
                    pass

            db.close()

            # Filter by min_similarity
            filtered_groups = [
                group
                for group in all_duplicate_groups
                if group["similarity"] >= min_similarity
            ]

            # Sort by similarity (descending) and number of occurrences
            filtered_groups.sort(
                key=lambda x: (x["similarity"], len(x["occurrences"])), reverse=True
            )

            return SuccessResult(
                data={
                    "duplicate_groups": filtered_groups,
                    "total_groups": len(filtered_groups),
                    "total_occurrences": sum(
                        len(g["occurrences"]) for g in filtered_groups
                    ),
                    "min_lines": min_lines,
                    "min_similarity": min_similarity,
                }
            )
        except Exception as e:
            return self._handle_error(e, "FIND_DUPLICATES_ERROR", "find_duplicates")

    @classmethod
    def metadata(cls: type["FindDuplicatesMCPCommand"]) -> Dict[str, Any]:
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
                "The find_duplicates command finds duplicate code blocks using AST normalization "
                "and optional semantic vector analysis. It identifies code that can be refactored "
                "to reduce duplication.\n\n"
                "Operation flow:\n"
                "1. Validates root_dir exists and is a directory\n"
                "2. Opens database connection\n"
                "3. Resolves project_id (from parameter or inferred from root_dir)\n"
                "4. Initializes DuplicateDetector with specified parameters\n"
                "5. If use_semantic=True:\n"
                "   - Initializes SVO client manager for semantic search\n"
                "   - Falls back to AST-only if semantic initialization fails\n"
                "6. If file_path provided:\n"
                "   - Analyzes specific file using AST parsing\n"
                "   - Finds duplicates within the file\n"
                "7. If file_path not provided:\n"
                "   - Analyzes all files in project\n"
                "   - Finds duplicates across all files\n"
                "8. Filters results by min_similarity threshold\n"
                "9. Sorts by similarity and number of occurrences\n"
                "10. Returns duplicate groups with occurrences\n\n"
                "Detection Methods:\n"
                "- AST normalization: Normalizes AST structures to find structural duplicates\n"
                "- Semantic vectors: Uses embeddings to find logical duplicates (if enabled)\n"
                "- Hybrid mode: Combines both methods for comprehensive detection\n\n"
                "Use cases:\n"
                "- Find code duplication for refactoring opportunities\n"
                "- Identify repeated patterns that can be extracted\n"
                "- Detect copy-paste code blocks\n"
                "- Find logical duplicates (semantically similar code)\n\n"
                "Important notes:\n"
                "- Skips files with syntax errors\n"
                "- Results sorted by similarity (highest first) and occurrence count\n"
                "- Semantic detection requires SVO service (falls back to AST if unavailable)\n"
                "- Each duplicate group contains multiple occurrences"
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
                        "If provided, only finds duplicates within this file. "
                        "If omitted, finds duplicates across all files in project."
                    ),
                    "type": "string",
                    "required": False,
                },
                "min_lines": {
                    "description": (
                        "Minimum lines for duplicate block. Default is 5. "
                        "Only blocks with at least min_lines are considered."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 5,
                },
                "min_similarity": {
                    "description": (
                        "Minimum similarity threshold (0.0-1.0). Default is 0.8 (80%). "
                        "Only duplicates with similarity >= min_similarity are returned."
                    ),
                    "type": "number",
                    "required": False,
                    "default": 0.8,
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "use_semantic": {
                    "description": (
                        "Use semantic vectors for finding logical duplicates. Default is True. "
                        "Requires SVO service. Falls back to AST-only if semantic search unavailable."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "semantic_threshold": {
                    "description": (
                        "Minimum semantic similarity threshold (0.0-1.0). Default is 0.85 (85%). "
                        "Only used when use_semantic=True."
                    ),
                    "type": "number",
                    "required": False,
                    "default": 0.85,
                    "minimum": 0.0,
                    "maximum": 1.0,
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
                    "description": "Find duplicates in specific file",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "file_path": "src/main.py",
                    },
                    "explanation": (
                        "Finds duplicate code blocks within src/main.py file."
                    ),
                },
                {
                    "description": "Find duplicates across project with AST only",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "use_semantic": False,
                    },
                    "explanation": (
                        "Finds structural duplicates using AST normalization only, "
                        "without semantic analysis."
                    ),
                },
                {
                    "description": "Find significant duplicates (10+ lines, 90% similarity)",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "min_lines": 10,
                        "min_similarity": 0.9,
                    },
                    "explanation": (
                        "Finds duplicates with at least 10 lines and 90% similarity. "
                        "Focuses on significant duplication."
                    ),
                },
                {
                    "description": "Find logical duplicates with semantic search",
                    "command": {
                        "root_dir": "/home/user/projects/my_project",
                        "use_semantic": True,
                        "semantic_threshold": 0.9,
                    },
                    "explanation": (
                        "Finds logical duplicates using semantic vectors with 90% similarity threshold."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "root_dir='/path' but project not registered",
                    "solution": "Ensure project is registered. Run update_indexes first.",
                },
                "FIND_DUPLICATES_ERROR": {
                    "description": "General error during duplicate detection",
                    "example": "Database error, AST parsing error, or semantic service unavailable",
                    "solution": (
                        "Check database integrity, verify file paths. "
                        "If semantic search fails, command falls back to AST-only detection."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "duplicate_groups": (
                            "List of duplicate groups. Each group contains:\n"
                            "- similarity: Similarity score (0.0-1.0)\n"
                            "- occurrences: List of occurrences, each with:\n"
                            "  - file_path: File where duplicate occurs\n"
                            "  - start_line: Starting line number\n"
                            "  - end_line: Ending line number\n"
                            "  - code: Code snippet (normalized)"
                        ),
                        "total_groups": "Total number of duplicate groups found",
                        "total_occurrences": "Total number of duplicate occurrences across all groups",
                        "min_lines": "Minimum lines threshold used",
                        "min_similarity": "Minimum similarity threshold used",
                    },
                    "example": {
                        "duplicate_groups": [
                            {
                                "similarity": 0.95,
                                "occurrences": [
                                    {
                                        "file_path": "src/utils.py",
                                        "start_line": 10,
                                        "end_line": 20,
                                        "code": "def helper(x):\n    return x * 2",
                                    },
                                    {
                                        "file_path": "src/main.py",
                                        "start_line": 42,
                                        "end_line": 52,
                                        "code": "def helper(x):\n    return x * 2",
                                    },
                                ],
                            },
                        ],
                        "total_groups": 1,
                        "total_occurrences": 2,
                        "min_lines": 5,
                        "min_similarity": 0.8,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, FIND_DUPLICATES_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use min_lines to filter out small duplicates",
                "Use min_similarity to focus on high-confidence duplicates",
                "Start with AST-only detection (use_semantic=False) for faster results",
                "Use semantic search for finding logical duplicates (similar functionality)",
                "Analyze specific files first before running project-wide detection",
                "Review duplicate groups sorted by similarity to prioritize refactoring",
                "Combine with comprehensive_analysis for complete code quality overview",
            ],
        }
