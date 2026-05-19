"""
MCP command: cst_unload_tree

Remove a CST tree from server memory by tree_id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict

from mcp_proxy_adapter.commands.result import SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.tree_builder import remove_tree


class CSTUnloadTreeCommand(BaseMCPCommand):
    """Remove a CST tree from memory."""

    name = "cst_unload_tree"
    version = "1.0.0"
    descr = (
        "Remove a CST tree from memory by tree_id. Use to free RAM after analysis."
    )
    category = "cst"
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
                    "description": "Tree ID returned by cst_load_file",
                },
            },
            "required": ["tree_id"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["CSTUnloadTreeCommand"]) -> Dict[str, Any]:
        from .zero_arg_commands_metadata import cst_unload_tree_metadata

        return cst_unload_tree_metadata(cls)

    async def execute(self, tree_id: str, **kwargs: Any) -> SuccessResult:
        was_present = remove_tree(tree_id)
        return SuccessResult(
            data={"tree_id": tree_id, "was_present": was_present}
        )
