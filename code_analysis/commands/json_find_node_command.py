"""
MCP command: json_find_node

Resolve a JSON element by JSON Pointer and/or simple key path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Union

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.json_tree.json_query import normalize_key_path, resolve_node_id_from_pointer
from ..core.json_tree.tree_builder import get_tree

logger = logging.getLogger(__name__)


class JsonFindNodeCommand(BaseMCPCommand):
    name = "json_find_node"
    version = "1.0.0"
    descr = "Find node_id by json_pointer and/or key_path (exact match)"
    category = "json"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tree_id": {"type": "string"},
                "json_pointer": {
                    "type": "string",
                    "description": "RFC 6901 pointer to value",
                },
                "key_path": {
                    "description": "Simple dotted path or list segments",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array"},
                    ],
                },
            },
            "required": ["tree_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        tree_id: str,
        json_pointer: Optional[str] = None,
        key_path: Optional[Union[str, List[Any]]] = None,
        **kwargs: Any,
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            tree = get_tree(tree_id)
            if not tree:
                return ErrorResult(
                    message=f"Tree not found: {tree_id}",
                    code="TREE_NOT_FOUND",
                    details={"tree_id": tree_id},
                )

            if json_pointer is None and key_path is None:
                return ErrorResult(
                    message="Provide json_pointer and/or key_path",
                    code="MISSING_QUERY",
                    details={},
                )

            pointers: List[str] = []
            if json_pointer is not None:
                pointers.append(json_pointer)
            if key_path is not None:
                kp = normalize_key_path(key_path)
                if json_pointer is None:
                    pointers.append(kp)
                elif kp != json_pointer:
                    return ErrorResult(
                        message="key_path does not match json_pointer",
                        code="QUERY_MISMATCH",
                        details={"json_pointer": json_pointer, "key_path_resolved": kp},
                    )

            # De-duplicate while preserving order
            seen = set()
            uniq: List[str] = []
            for p in pointers:
                if p not in seen:
                    seen.add(p)
                    uniq.append(p)

            results = []
            for p in uniq:
                nid = resolve_node_id_from_pointer(tree, p)
                results.append(
                    {
                        "json_pointer": p,
                        "node_id": nid,
                        "found": nid is not None,
                    }
                )

            logger.info(
                "[TIMING] command=json_find_node elapsed_sec=%.4f",
                time.perf_counter() - t_start,
            )
            return SuccessResult(
                data={
                    "success": True,
                    "tree_id": tree_id,
                    "matches": results,
                }
            )
        except Exception as e:
            logger.exception("json_find_node failed: %s", e)
            return ErrorResult(
                message=f"json_find_node failed: {e}", code="JSON_FIND_NODE_ERROR"
            )

    @classmethod
    def metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
        }
