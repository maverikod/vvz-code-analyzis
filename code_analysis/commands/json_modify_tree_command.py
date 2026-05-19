"""
MCP command: json_modify_tree

Structured edits: replace, insert, delete (in-memory until json_save_tree).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.json_tree.tree_builder import get_tree
from ..core.json_tree.tree_modifier import modify_tree

logger = logging.getLogger(__name__)


def _json_modify_schema() -> Dict[str, Any]:
    op = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["replace", "delete", "insert"],
            },
            "node_id": {"type": "string"},
            "json_pointer": {"type": "string"},
            "parent_node_id": {"type": "string"},
            "parent_json_pointer": {"type": "string"},
            "value": {},
            "key": {"type": "string", "description": "Object key for insert"},
            "index": {
                "type": "integer",
                "description": "Array index for insert (omit to append)",
            },
        },
        "required": ["action"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "tree_id": {"type": "string"},
            "operations": {"type": "array", "items": op},
            "preview": {
                "type": "boolean",
                "default": False,
                "description": "Reserved; in-memory modify always applies",
            },
        },
        "required": ["tree_id", "operations"],
        "additionalProperties": False,
    }


class JsonModifyTreeCommand(BaseMCPCommand):
    name = "json_modify_tree"
    version = "1.0.0"
    descr = "Apply replace / delete / insert operations to JSON tree session"
    category = "json"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return _json_modify_schema()

    async def execute(
        self,
        tree_id: str,
        operations: List[Dict[str, Any]],
        preview: bool = False,
        **kwargs: Any,
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            if not get_tree(tree_id):
                return ErrorResult(
                    message=f"Tree not found: {tree_id}",
                    code="TREE_NOT_FOUND",
                    details={"tree_id": tree_id},
                )
            if preview:
                return ErrorResult(
                    message="preview is not implemented for json_modify_tree",
                    code="NOT_IMPLEMENTED",
                    details={},
                )

            modify_tree(tree_id, operations)
            updated = get_tree(tree_id)
            assert updated is not None
            nodes = [m.to_dict() for m in updated.metadata_map.values()]
            logger.info(
                "[TIMING] command=json_modify_tree ops=%d elapsed_sec=%.4f",
                len(operations),
                time.perf_counter() - t_start,
            )
            return SuccessResult(
                data={
                    "success": True,
                    "tree_id": tree_id,
                    "total_nodes": len(nodes),
                    "nodes": nodes,
                }
            )
        except (ValueError, KeyError, TypeError) as e:
            return ErrorResult(
                message=str(e),
                code="INVALID_OPERATION",
                details={"error": str(e)},
            )
        except Exception as e:
            logger.exception("json_modify_tree failed: %s", e)
            return ErrorResult(
                message=f"json_modify_tree failed: {e}", code="JSON_MODIFY_ERROR"
            )

    @classmethod
    def metadata(cls: type["JsonModifyTreeCommand"]) -> Dict[str, Any]:
        from .json_tree_commands_metadata import json_tree_command_metadata

        return json_tree_command_metadata(
            cls,
            operation="modify_tree",
            detailed_description=cls.descr,
            example_params={
                "tree_id": "550e8400-e29b-41d4-a716-446655440000",
                "operations": [],
            },
        )
