"""
MCP command: query_cst

Find LibCST nodes by CSTQuery selector.

This command is designed for "logical block" refactor workflows:
- discover target nodes with `query_cst`
- patch modules with `compose_cst_module` using `node_id` (or `cst_query`) selectors

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .query_cst_handler import (
    build_ops_from_replacements,
    resolve_target_file,
    run_replace_flow,
    validate_query_mode,
    validate_replacements,
)
from .query_cst_metadata import get_query_cst_metadata
from ..core.cst_module import ReplaceOp, Selector
from ..core.exceptions import QueryParseError
from ..cst_query import query_source

logger = logging.getLogger(__name__)


class QueryCSTCommand(BaseMCPCommand):
    name = "query_cst"
    version = "1.1.0"
    descr = "Query python source using CSTQuery selectors; optional find+replace in one call"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        base_props = cls._get_base_schema_properties()
        return {
            "type": "object",
            "properties": {
                **base_props,
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (relative to project root)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSTQuery selector string",
                },
                "include_code": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include code snippets for each match (can be large)",
                },
                "max_results": {
                    "type": "integer",
                    "default": 200,
                    "description": "Maximum number of matches to return",
                },
                "replace_with": {
                    "type": "string",
                    "description": (
                        "If set, replace the matched node(s) with this code (single string). "
                        "Use code_lines for multi-line to avoid escaping. One call = find + replace."
                    ),
                },
                "code_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "If set, replace the matched node(s) with these lines (joined by newline). "
                        "Prefer over replace_with for multi-line code."
                    ),
                },
                "match_index": {
                    "type": "integer",
                    "default": 0,
                    "description": (
                        "When replacing: which match to replace (0-based). "
                        "Ignored if replace_all is true."
                    ),
                },
                "replace_all": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When replacing: if true, replace all matches with the same new code. "
                        "match_index is ignored."
                    ),
                },
                "replacements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "match_index": {"type": "integer"},
                            "replace_with": {"type": "string"},
                            "code_lines": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["match_index"],
                    },
                    "description": (
                        "When set: replace multiple matches with different code per match. "
                        "Each entry: match_index (0-based) and either replace_with or code_lines. "
                        "Ignored if replace_with/code_lines (single-code path) is used."
                    ),
                },
                "start_line": {
                    "type": "integer",
                    "description": (
                        "1-based start line for range-based replace. "
                        "When used with end_line (and replace_with/code_lines), replace the statement(s) covering this range. "
                        "Optional; if both start_line and end_line are set, range replace is used (selector optional)."
                    ),
                },
                "end_line": {
                    "type": "integer",
                    "description": (
                        "1-based end line for range-based replace. "
                        "Must be >= start_line. When both start_line and end_line are set, replace that line range."
                    ),
                },
                "preview": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "If true, run replace in memory and return diff/modified_source without writing to file. "
                        "No backup, no file change."
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "Alias for preview: if true, same as preview=true.",
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        selector: Optional[str] = None,
        include_code: bool = False,
        max_results: int = 200,
        replace_with: Optional[str] = None,
        code_lines: Optional[List[str]] = None,
        match_index: int = 0,
        replace_all: bool = False,
        replacements: Optional[List[Dict[str, Any]]] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        preview: bool = False,
        dry_run: bool = False,
        **kwargs,
    ) -> SuccessResult:
        t_start = time.perf_counter()
        preview_mode = preview or dry_run
        try:
            t0 = time.perf_counter()
            resolved = resolve_target_file(self, project_id, file_path)
            if isinstance(resolved, ErrorResult):
                return resolved
            root_path, target = resolved
            logger.info(
                "[TIMING] command=query_cst step=resolve_path elapsed_sec=%.4f",
                time.perf_counter() - t0,
            )
            source = target.read_text(encoding="utf-8")
            file_lines = len(source.splitlines()) or 1

            use_replacements_list = replacements is not None and len(replacements) > 0
            is_replace_mode = (
                use_replacements_list
                or replace_with is not None
                or code_lines is not None
            )
            range_only = start_line is not None and end_line is not None

            err = validate_query_mode(
                is_replace_mode,
                selector,
                range_only,
                start_line,
                end_line,
                file_lines,
                use_replacements_list,
            )
            if err is not None:
                return err

            if range_only:
                selector_for_query = selector or ""
                matches = []
            else:
                selector_for_query = selector or ""
                t_query = time.perf_counter()
                matches = query_source(
                    source, selector_for_query, include_code=include_code
                )
            if not range_only:
                logger.info(
                    "[TIMING] command=query_cst step=query_source matches=%d elapsed_sec=%.4f",
                    len(matches),
                    time.perf_counter() - t_query,
                )
            single_new_code: Optional[str] = None
            new_code_by_index: Optional[Dict[int, str]] = None
            ops: List[ReplaceOp] = []
            if range_only and is_replace_mode:
                assert start_line is not None and end_line is not None
                single_new_code = (
                    "\n".join(code_lines)
                    if code_lines is not None
                    else (replace_with or "")
                )
                ops = [
                    ReplaceOp(
                        Selector(
                            kind="range",
                            start_line=start_line,
                            end_line=end_line,
                        ),
                        single_new_code,
                    )
                ]
            elif (
                use_replacements_list
                or replace_with is not None
                or code_lines is not None
            ):
                if not matches:
                    return ErrorResult(
                        message="No matches found for selector; nothing to replace",
                        code="CST_QUERY_NO_MATCH",
                        details={"selector": selector_for_query},
                    )
                if use_replacements_list:
                    # Replacements list: different code per match_index
                    assert replacements is not None  # ensured by use_replacements_list
                    err = validate_replacements(
                        replacements, len(matches), selector_for_query
                    )
                    if err is not None:
                        return err
                    ops, new_code_by_index = build_ops_from_replacements(
                        selector_for_query, replacements
                    )
                else:
                    # Legacy single-code path
                    single_new_code = (
                        "\n".join(code_lines)
                        if code_lines is not None
                        else (replace_with or "")
                    )
                    if replace_all:
                        ops = [
                            ReplaceOp(
                                Selector(
                                    kind="cst_query",
                                    query=selector_for_query,
                                    match_index=i,
                                ),
                                single_new_code,
                            )
                            for i in range(len(matches))
                        ]
                    else:
                        if match_index < 0 or match_index >= len(matches):
                            return ErrorResult(
                                message=(
                                    f"match_index {match_index} out of range "
                                    f"(selector matched {len(matches)} node(s))"
                                ),
                                code="CST_QUERY_MATCH_INDEX",
                                details={
                                    "selector": selector_for_query,
                                    "match_index": match_index,
                                    "match_count": len(matches),
                                },
                            )
                        ops = [
                            ReplaceOp(
                                Selector(
                                    kind="cst_query",
                                    query=selector_for_query,
                                    match_index=match_index,
                                ),
                                single_new_code,
                            )
                        ]
                    new_code_by_index = None

            if ops:
                return run_replace_flow(
                    self,
                    root_path,
                    target,
                    source,
                    ops,
                    file_path,
                    project_id,
                    preview_mode,
                    selector_for_query,
                    t_start,
                    matches,
                    range_only,
                    replace_all and not use_replacements_list,
                    match_index,
                    single_new_code,
                    new_code_by_index,
                )

            # Query-only mode
            truncated = False
            if max_results >= 0 and len(matches) > max_results:
                matches = matches[:max_results]
                truncated = True

            data = {
                "success": True,
                "file_path": str(target),
                "selector": selector_for_query,
                "truncated": truncated,
                "matches": [
                    {
                        "node_id": m.node_id,
                        "kind": m.kind,
                        "type": m.node_type,
                        "name": m.name,
                        "qualname": m.qualname,
                        "start_line": m.start_line,
                        "start_col": m.start_col,
                        "end_line": m.end_line,
                        "end_col": m.end_col,
                        "code": m.code,
                    }
                    for m in matches
                ],
            }
            logger.info(
                "[TIMING] command=query_cst total_elapsed_sec=%.4f",
                time.perf_counter() - t_start,
            )
            return SuccessResult(data=data)
        except QueryParseError as e:
            return ErrorResult(
                message=f"Invalid selector: {e}",
                code="CST_QUERY_PARSE_ERROR",
                details={"selector": selector or ""},
            )
        except Exception as e:
            logger.exception("query_cst failed: %s", e)
            return ErrorResult(message=f"query_cst failed: {e}", code="CST_QUERY_ERROR")

    @classmethod
    def metadata(cls: type["QueryCSTCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return get_query_cst_metadata(cls)
