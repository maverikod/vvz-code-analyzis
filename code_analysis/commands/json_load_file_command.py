"""
MCP command: json_load_file

Load a .json file into an in-memory JSON tree session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.file_lock import file_lock
from ..core.json_tree.tree_builder import load_file_to_tree

logger = logging.getLogger(__name__)


class JsonLoadFileCommand(BaseMCPCommand):
    """Load .json file into indexed session (tree_id)."""

    name = "json_load_file"
    version = "1.0.0"
    descr = "Load a .json file into an in-memory tree session and return tree_id with node metadata"
    category = "json"
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
                    "description": "Path to .json file relative to project root",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    async def execute(
        self, project_id: str, file_path: str, **kwargs: Any
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            database = self._open_database_from_config(auto_analyze=False)
            try:
                target = self._resolve_file_path_from_project(
                    database, project_id, file_path
                )
                if target.suffix.lower() != ".json":
                    return ErrorResult(
                        message="json_load_file only supports .json files",
                        code="INVALID_FILE",
                        details={"file_path": str(target)},
                    )
            finally:
                database.disconnect()

            if not target.exists():
                return ErrorResult(
                    message=f"File not found: {target}",
                    code="FILE_NOT_FOUND",
                    details={"file_path": str(target)},
                )

            with file_lock(target):
                tree = load_file_to_tree(str(target))

            nodes = [m.to_dict() for m in tree.metadata_map.values()]
            logger.info(
                "[TIMING] command=json_load_file nodes=%d elapsed_sec=%.4f",
                len(nodes),
                time.perf_counter() - t_start,
            )
            return SuccessResult(
                data={
                    "success": True,
                    "tree_id": tree.tree_id,
                    "file_path": tree.file_path,
                    "root_node_id": tree.root_node_id,
                    "nodes": nodes,
                    "total_nodes": len(nodes),
                }
            )
        except ValueError as e:
            return ErrorResult(
                message=str(e),
                code="INVALID_JSON",
                details={"error": str(e)},
            )
        except Exception as e:
            logger.exception("json_load_file failed: %s", e)
            return ErrorResult(
                message=f"json_load_file failed: {e}", code="JSON_LOAD_ERROR"
            )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
        }
