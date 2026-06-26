"""
MCP command: json_reload_tree

Reload JSON document from disk into the same tree_id session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.json_tree.tree_builder import reload_tree_from_file

logger = logging.getLogger(__name__)


class JsonReloadTreeCommand(BaseMCPCommand):
    """Reload a JSON tree session from its source file on disk."""

    name = "json_reload_tree"
    version = "1.0.0"
    descr = "Reload .json from disk into existing session (same tree_id)"
    category = "json"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "tree_id": {"type": "string"},
            },
            "required": ["tree_id"],
            "additionalProperties": False,
        }

    async def execute(self, tree_id: str, **kwargs: Any) -> SuccessResult:
        """Refresh an existing JSON tree session while preserving its tree id."""
        t_start = time.perf_counter()
        try:
            updated = reload_tree_from_file(tree_id)
            if not updated:
                return ErrorResult(
                    message=f"Tree not found: {tree_id}",
                    code="TREE_NOT_FOUND",
                    details={"tree_id": tree_id},
                )
            nodes = [m.to_dict() for m in updated.metadata_map.values()]
            logger.info(
                "[TIMING] command=json_reload_tree nodes=%d elapsed_sec=%.4f",
                len(nodes),
                time.perf_counter() - t_start,
            )
            return SuccessResult(
                data={
                    "success": True,
                    "tree_id": updated.tree_id,
                    "file_path": updated.file_path,
                    "nodes": nodes,
                    "total_nodes": len(nodes),
                    "reloaded": True,
                }
            )
        except FileNotFoundError as e:
            return ErrorResult(
                message=str(e),
                code="FILE_NOT_FOUND",
                details={"tree_id": tree_id},
            )
        except ValueError as e:
            return ErrorResult(
                message=str(e),
                code="INVALID_JSON",
                details={"error": str(e)},
            )
        except Exception as e:
            logger.exception("json_reload_tree failed: %s", e)
            return ErrorResult(
                message=f"json_reload_tree failed: {e}", code="JSON_RELOAD_ERROR"
            )

    @classmethod
    def metadata(cls: type["JsonReloadTreeCommand"]) -> Dict[str, Any]:
        """Return metadata for the JSON tree reload command."""
        from .json_tree_commands_metadata import json_tree_command_metadata

        return json_tree_command_metadata(
            cls,
            operation="reload_tree",
            detailed_description=cls.descr,
            example_params={
                "tree_id": "550e8400-e29b-41d4-a716-446655440000",
                "project_id": "550e8400-e29b-41d4-a716-446655440001",
                "file_path": "config/settings.json",
            },
        )
