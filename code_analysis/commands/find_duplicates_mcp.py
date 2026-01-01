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
