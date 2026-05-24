"""
MCP command: json_get_node_info

Structured info for a JSON element by node id, JSON Pointer, or simple key path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Union

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.exceptions import ValidationError
from ..core.json_tree.json_pointer import get_value_at
from ..core.json_tree.json_query import normalize_key_path, resolve_node_id_from_pointer
from ..core.json_tree.tree_builder import get_tree

logger = logging.getLogger(__name__)


class JsonGetNodeInfoCommand(BaseMCPCommand):
    name = "json_get_node_info"
    version = "1.0.0"
    descr = "Get metadata for a JSON value by node_id, json_pointer, or key_path; optional fragment"
    category = "json"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tree_id": {
                    "type": "string",
                    "description": "Session from json_load_file",
                },
                "node_id": {"type": "string", "description": "Stable node id"},
                "json_pointer": {
                    "type": "string",
                    "description": "RFC 6901 pointer (use '' for root)",
                },
                "key_path": {
                    "description": "Simple path: 'a.b.0' or list segments ['a','b',0]",
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array"},
                    ],
                },
                "include_fragment": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include JSON-serialized value fragment",
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
        """Validate address params and key_path oneOf before execute."""
        params = super().validate_params(params)
        node_id = params.get("node_id")
        json_pointer = params.get("json_pointer")
        key_path = params.get("key_path")
        if node_id is None and json_pointer is None and key_path is None:
            raise ValidationError(
                f"{self.name}: provide one of: node_id, json_pointer, key_path",
                field="node_id",
                details={},
            )
        if key_path is not None:
            self._validate_key_path_param(key_path, command_name=self.name)
        return params

    async def execute(
        self,
        tree_id: str,
        node_id: Optional[str] = None,
        json_pointer: Optional[str] = None,
        key_path: Optional[Union[str, List[Any]]] = None,
        include_fragment: bool = False,
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

            pointer: Optional[str] = None
            if node_id:
                pointer = tree.pointer_by_id.get(node_id)
                if pointer is None:
                    return ErrorResult(
                        message=f"Unknown node_id: {node_id}",
                        code="NODE_NOT_FOUND",
                        details={"node_id": node_id},
                    )
            elif json_pointer is not None:
                pointer = json_pointer
            elif key_path is not None:
                pointer = normalize_key_path(key_path)
            else:
                return ErrorResult(
                    message="Provide one of: node_id, json_pointer, key_path",
                    code="MISSING_ADDRESS",
                    details={},
                )

            assert pointer is not None
            nid = resolve_node_id_from_pointer(tree, pointer)
            if nid is None:
                return ErrorResult(
                    message=f"No value at pointer: {pointer!r}",
                    code="NODE_NOT_FOUND",
                    details={"json_pointer": pointer},
                )

            meta = tree.metadata_map[nid]
            value = get_value_at(tree.root_data, pointer)
            data: Dict[str, Any] = {
                "success": True,
                "tree_id": tree_id,
                "node_id": nid,
                "json_pointer": pointer,
                "metadata": meta.to_dict(),
            }
            if include_fragment:
                data["fragment"] = value
                data["fragment_json"] = json.dumps(value, indent=2, ensure_ascii=False)

            logger.info(
                "[TIMING] command=json_get_node_info elapsed_sec=%.4f",
                time.perf_counter() - t_start,
            )
            return SuccessResult(data=data)
        except Exception as e:
            logger.exception("json_get_node_info failed: %s", e)
            return ErrorResult(
                message=f"json_get_node_info failed: {e}", code="JSON_GET_NODE_ERROR"
            )

    @classmethod
    def metadata(cls: type["JsonGetNodeInfoCommand"]) -> Dict[str, Any]:
        from .json_tree_commands_metadata import json_tree_command_metadata

        return json_tree_command_metadata(
            cls,
            operation="get_node_info",
            detailed_description=cls.descr,
            example_params={
                "tree_id": "550e8400-e29b-41d4-a716-446655440000",
                "node_id": "550e8400-e29b-41d4-a716-446655440001",
            },
        )
