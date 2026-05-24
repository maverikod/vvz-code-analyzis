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
from ..core.exceptions import ValidationError
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
                    "description": "Simple dotted path or list of string segments",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                },
            },
            "required": ["tree_id"],
            "additionalProperties": False,
        }

    @staticmethod
    def _validate_key_path_param(key_path: Any, *, command_name: str) -> None:
        """Enforce key_path oneOf: string or array of strings."""
        if isinstance(key_path, str):
            return
        if isinstance(key_path, list):
            for index, item in enumerate(key_path):
                if not isinstance(item, str):
                    raise ValidationError(
                        f"{command_name}: parameter 'key_path' array items must be "
                        f"strings, got {type(item).__name__} at index {index}",
                        field="key_path",
                        details={"index": index, "item_type": type(item).__name__},
                    )
            return
        raise ValidationError(
            f"{command_name}: parameter 'key_path' must be string or array of "
            f"strings, got {type(key_path).__name__}",
            field="key_path",
            details={},
        )

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate json_pointer/key_path types and require at least one query param."""
        params = super().validate_params(params)
        json_pointer = params.get("json_pointer")
        key_path = params.get("key_path")
        if json_pointer is None and key_path is None:
            raise ValidationError(
                f"{self.name}: provide json_pointer and/or key_path",
                field="json_pointer",
                details={},
            )
        if key_path is not None:
            self._validate_key_path_param(key_path, command_name=self.name)
        return params

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
    def metadata(cls: type["JsonFindNodeCommand"]) -> Dict[str, Any]:
        from .json_tree_commands_metadata import json_tree_command_metadata

        return json_tree_command_metadata(
            cls,
            operation="find_node",
            detailed_description=cls.descr,
            example_params={
                "tree_id": "550e8400-e29b-41d4-a716-446655440000",
                "json_pointer": "/items/0",
            },
        )
