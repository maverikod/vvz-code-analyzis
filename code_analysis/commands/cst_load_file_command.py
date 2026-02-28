"""
MCP command: cst_load_file

Load Python file into CST tree and return tree_id with node metadata.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import libcst as cst
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .cst_load_file_helpers import (
    MAX_SYNTAX_FIX_ITERATIONS,
    apply_syntax_error_fix,
    build_load_response,
)
from .cst_load_file_metadata import get_cst_load_file_metadata
from ..core.file_lock import file_lock
from ..core.cst_tree.tree_builder import load_file_to_tree
from ..core.cst_tree.tree_metadata import get_node_parent
from ..core.cst_tree.tree_range_finder import find_node_by_range

logger = logging.getLogger(__name__)


class CSTLoadFileCommand(BaseMCPCommand):
    """Load file into CST tree."""

    name = "cst_load_file"
    version = "1.0.0"
    descr = "Load Python file into CST tree and return tree_id with node metadata"
    category = "cst"
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
                    "description": "Target Python file path (relative to project root)",
                },
                "node_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter by node types (e.g., ['FunctionDef', 'ClassDef'])",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Optional maximum depth for node filtering",
                },
                "include_children": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether to include children information in metadata",
                },
                "return_format": {
                    "type": "string",
                    "enum": ["full", "skeleton"],
                    "default": "full",
                    "description": (
                        "full: return tree_id and full node list. "
                        "skeleton: return tree_id and collapsed view (signatures, docstrings, body=comment+pass)."
                    ),
                },
                "selector": {
                    "description": (
                        "Optional: XPath-like selector string or list of node_ids. "
                        "When set, response includes selected_nodes with content (code) for matching nodes."
                    ),
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        node_types: Optional[List[str]] = None,
        max_depth: Optional[int] = None,
        include_children: bool = True,
        return_format: str = "full",
        selector: Optional[Any] = None,
        **kwargs: Any,
    ) -> SuccessResult:
        t_start = time.perf_counter()
        try:
            t0 = time.perf_counter()
            database = self._open_database_from_config(auto_analyze=False)
            try:
                target = self._resolve_file_path_from_project(
                    database, project_id, file_path
                )
                if target.suffix != ".py":
                    return ErrorResult(
                        message="Target file must be a .py file",
                        code="INVALID_FILE",
                        details={"file_path": str(target)},
                    )
            finally:
                database.disconnect()
            logger.info(
                "[TIMING] command=cst_load_file step=resolve_path elapsed_sec=%.4f",
                time.perf_counter() - t0,
            )

            t0 = time.perf_counter()
            path_tmp_clean = Path(str(target) + ".tmp")
            if path_tmp_clean.exists():
                path_tmp_clean.unlink()
            logger.info(
                "[TIMING] command=cst_load_file step=cleanup_tmp elapsed_sec=%.4f",
                time.perf_counter() - t0,
            )

            tree = None
            path_tmp: Optional[Path] = None
            commented_lines_info: List[Dict[str, Any]] = []

            with file_lock(target):
                t0 = time.perf_counter()
                try:
                    tree = load_file_to_tree(
                        str(target),
                        node_types=node_types,
                        max_depth=max_depth,
                        include_children=include_children,
                    )
                except cst.ParserSyntaxError:
                    logger.info(
                        "[TIMING] command=cst_load_file step=load_tree elapsed_sec=%.4f (syntax_error)",
                        time.perf_counter() - t0,
                    )
                    t0 = time.perf_counter()
                    path_tmp = Path(str(target) + ".tmp")
                    shutil.copy2(target, path_tmp)
                    lines = path_tmp.read_text(encoding="utf-8").split("\n")
                    for _ in range(MAX_SYNTAX_FIX_ITERATIONS):
                        try:
                            cst.parse_module("\n".join(lines))
                            break
                        except cst.ParserSyntaxError as e:
                            lines, comment_line_no = apply_syntax_error_fix(lines, e)
                            commented_lines_info.append(
                                {
                                    "line": comment_line_no,
                                    "error": str(e).strip(),
                                }
                            )
                    else:
                        raise ValueError(
                            f"Syntax fix did not converge after "
                            f"{MAX_SYNTAX_FIX_ITERATIONS} iterations"
                        )
                    path_tmp.write_text("\n".join(lines), encoding="utf-8")
                    logger.info(
                        "[TIMING] command=cst_load_file step=syntax_fix_loop elapsed_sec=%.4f",
                        time.perf_counter() - t0,
                    )
                    t0 = time.perf_counter()
                    tree = load_file_to_tree(
                        str(path_tmp),
                        node_types=node_types,
                        max_depth=max_depth,
                        include_children=include_children,
                    )
                    logger.info(
                        "[TIMING] command=cst_load_file step=load_tree_from_tmp elapsed_sec=%.4f",
                        time.perf_counter() - t0,
                    )
                    t0 = time.perf_counter()
                    for info in commented_lines_info:
                        line_no = info["line"]
                        node = find_node_by_range(
                            tree.tree_id,
                            line_no,
                            line_no,
                            prefer_exact=False,
                        )
                        parent = None
                        if node:
                            parent_meta = get_node_parent(tree.tree_id, node.node_id)
                            if parent_meta:
                                parent = parent_meta.to_dict()
                        info["parent_node"] = parent
                    logger.info(
                        "[TIMING] command=cst_load_file step=parent_nodes elapsed_sec=%.4f",
                        time.perf_counter() - t0,
                    )
                else:
                    logger.info(
                        "[TIMING] command=cst_load_file step=load_tree elapsed_sec=%.4f",
                        time.perf_counter() - t0,
                    )

                t0 = time.perf_counter()
                data = build_load_response(
                    tree=tree,
                    target=target,
                    return_format=return_format,
                    selector=selector,
                    commented_lines_info=commented_lines_info,
                    path_tmp=path_tmp,
                )
                logger.info(
                    "[TIMING] command=cst_load_file step=build_response elapsed_sec=%.4f",
                    time.perf_counter() - t0,
                )
                logger.info(
                    "[TIMING] command=cst_load_file total_elapsed_sec=%.4f",
                    time.perf_counter() - t_start,
                )
                return SuccessResult(data=data)

        except FileNotFoundError as e:
            return ErrorResult(
                message=f"File not found: {e}",
                code="FILE_NOT_FOUND",
                details={"file_path": file_path},
            )
        except ValueError as e:
            return ErrorResult(
                message=f"Invalid file: {e}",
                code="INVALID_FILE",
                details={"file_path": file_path},
            )
        except Exception as e:
            logger.exception("cst_load_file failed: %s", e)
            return ErrorResult(
                message=f"cst_load_file failed: {e}", code="CST_LOAD_ERROR"
            )

    @classmethod
    def metadata(cls: type["CSTLoadFileCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_cst_load_file_metadata(cls)
