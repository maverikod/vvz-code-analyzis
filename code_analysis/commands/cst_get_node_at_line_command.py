"""
MCP command: cst_get_node_at_line

Return the node spanning a given line and its parent in one response.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from ..core.cst_tree.statement_ancestor import (
    annotate_statement_source,
    find_statement_ancestor_node_id,
)
from ..core.cst_tree.tree_builder import get_tree
from ..core.cst_tree.tree_metadata import get_node_metadata, get_node_parent
from ..core.cst_tree.tree_range_finder import find_node_by_range

logger = logging.getLogger(__name__)


class CSTGetNodeAtLineCommand(BaseMCPCommand):
    """Return node at line and its parent in one call."""

    name = "cst_get_node_at_line"
    version = "1.1.0"
    descr = (
        "Get the node at a line, optional statement-level ancestor with annotated "
        "source, and parent (reduces round-trips for CST edits)"
    )
    category = "cst"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        return {
            "type": "object",
            "properties": {
                "tree_id": {
                    "type": "string",
                    "description": "Tree ID from cst_load_file",
                },
                "line": {
                    "type": "integer",
                    "description": "Line number (1-based)",
                },
                "include_code": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include code snippet for node and parent",
                },
                "statement_level": {
                    "type": "boolean",
                    "default": True,
                    "description": (
                        "When true, include nearest statement-level ancestor with "
                        "line-annotated source plus a compact leaf summary. When false, "
                        "return only the deepest node and its parent (legacy shape)."
                    ),
                },
            },
            "required": ["tree_id", "line"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        tree_id: str,
        line: int,
        include_code: bool = False,
        statement_level: bool = True,
        **kwargs: Any,
    ) -> SuccessResult:
        """Return the CST node covering a line, with optional code and statement context."""
        t_start = time.perf_counter()
        try:
            if line < 1:
                return ErrorResult(
                    message="Line must be >= 1 (1-based)",
                    code="INVALID_LINE",
                    details={"tree_id": tree_id, "line": line},
                )

            node = find_node_by_range(tree_id, line, line, prefer_exact=False)
            if not node:
                return ErrorResult(
                    message=f"No node found at line {line}",
                    code="NODE_NOT_FOUND",
                    details={"tree_id": tree_id, "line": line},
                )

            node_meta: Optional[Any] = get_node_metadata(
                tree_id, node.node_id, include_code=include_code
            )
            if not node_meta:
                return ErrorResult(
                    message=f"Node metadata not found for node at line {line}",
                    code="NODE_NOT_FOUND",
                    details={"tree_id": tree_id, "line": line, "node_id": node.node_id},
                )

            parent_meta = get_node_parent(tree_id, node.node_id)
            parent_dict: Optional[Dict[str, Any]] = None
            if parent_meta:
                if include_code:
                    parent_with_code = get_node_metadata(
                        tree_id, parent_meta.node_id, include_code=True
                    )
                    parent_dict = (
                        parent_with_code.to_dict()
                        if parent_with_code
                        else parent_meta.to_dict()
                    )
                else:
                    parent_dict = parent_meta.to_dict()

            result: Dict[str, Any] = {
                "success": True,
                "tree_id": tree_id,
                "line": line,
                "node": node_meta.to_dict(),
                "parent": parent_dict,
            }

            if statement_level:
                tree = get_tree(tree_id)
                if not tree:
                    return ErrorResult(
                        message=f"Tree not found: {tree_id}",
                        code="TREE_NOT_FOUND",
                        details={"tree_id": tree_id, "line": line},
                    )
                stmt_id, stmt_fallback = find_statement_ancestor_node_id(
                    tree, node.node_id
                )
                stmt_meta = get_node_metadata(tree_id, stmt_id, include_code=True)
                if not stmt_meta:
                    return ErrorResult(
                        message="Statement ancestor metadata not found",
                        code="NODE_NOT_FOUND",
                        details={
                            "tree_id": tree_id,
                            "line": line,
                            "statement_node_id": stmt_id,
                        },
                    )
                raw_source = stmt_meta.code or ""
                start_ln = int(stmt_meta.start_line)
                annotated = annotate_statement_source(raw_source, start_ln)
                result["statement"] = {
                    "stable_id": stmt_meta.stable_id,
                    "type": stmt_meta.type,
                    "start_line": stmt_meta.start_line,
                    "end_line": stmt_meta.end_line,
                    "source": annotated,
                }
                result["leaf"] = {
                    "stable_id": node_meta.stable_id,
                    "type": node_meta.type,
                    "start_line": node_meta.start_line,
                    "end_line": node_meta.end_line,
                }
                if stmt_fallback:
                    result["fallback"] = True

            logger.info(
                "[TIMING] command=cst_get_node_at_line total_elapsed_sec=%.4f",
                time.perf_counter() - t_start,
            )
            return SuccessResult(data=result)

        except ValueError as e:
            return ErrorResult(
                message=str(e),
                code="INVALID_RANGE",
                details={"tree_id": tree_id, "line": line},
            )
        except Exception as e:
            logger.exception("cst_get_node_at_line failed: %s", e)
            return ErrorResult(
                message=f"cst_get_node_at_line failed: {e}",
                code="CST_GET_NODE_AT_LINE_ERROR",
            )
