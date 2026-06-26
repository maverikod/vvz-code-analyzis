"""
MCP command: cst_list_trees

List CST trees currently loaded in memory with TTL-related fields.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import time
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_builder import CST_TREE_TTL_SECONDS, _trees


class CSTListTreesCommand(BaseMCPCommand):
    """List loaded CST trees and idle/TTL status."""

    name = "cst_list_trees"
    version = "1.0.0"
    descr = "List all CST trees currently loaded in memory with their TTL status."
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["CSTListTreesCommand"]) -> Dict[str, Any]:
        """Return metadata for the zero-argument CST tree listing command."""
        from .zero_arg_commands_metadata import cst_list_trees_metadata

        return cst_list_trees_metadata(cls)

    async def execute(self, **kwargs: Any) -> SuccessResult:
        """Return loaded CST trees with idle time and TTL expiration details."""
        now = time.monotonic()
        trees = []
        for tree in _trees.values():
            idle = now - tree.last_accessed_at
            trees.append(
                {
                    "tree_id": tree.tree_id,
                    "file_path": tree.file_path,
                    "node_count": len(tree.node_map),
                    "loaded_ago_sec": round(now - tree.loaded_at),
                    "idle_sec": round(idle),
                    "ttl_expires_sec": round(CST_TREE_TTL_SECONDS - idle),
                }
            )
        return SuccessResult(data={"count": len(trees), "trees": trees})
