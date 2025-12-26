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
from pathlib import Path
from typing import Any, Dict

from mcp_proxy_adapter.commands.base import Command
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..cst_query import QueryParseError, query_source

logger = logging.getLogger(__name__)


class QueryCSTCommand(Command):
    name = "query_cst"
    version = "1.0.0"
    descr = "Query python source using CSTQuery selectors (LibCST)"
    category = "refactor"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {"type": "string", "description": "Project root directory"},
                "file_path": {
                    "type": "string",
                    "description": "Target python file path (absolute or relative to root_dir)",
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
            },
            "required": ["root_dir", "file_path", "selector"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        file_path: str,
        selector: str,
        include_code: bool = False,
        max_results: int = 200,
        **kwargs,
    ) -> SuccessResult:
        try:
            root = Path(root_dir).resolve()
            target = Path(file_path)
            if not target.is_absolute():
                target = (root / target).resolve()

            if target.suffix != ".py":
                return ErrorResult(
                    message="Target file must be a .py file",
                    code="INVALID_FILE",
                    details={"file_path": str(target)},
                )
            if not target.exists():
                return ErrorResult(
                    message="Target file does not exist",
                    code="FILE_NOT_FOUND",
                    details={"file_path": str(target)},
                )

            source = target.read_text(encoding="utf-8")
            matches = query_source(source, selector, include_code=include_code)
            truncated = False
            if max_results >= 0 and len(matches) > max_results:
                matches = matches[:max_results]
                truncated = True

            data = {
                "success": True,
                "file_path": str(target),
                "selector": selector,
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
            return SuccessResult(data=data)
        except QueryParseError as e:
            return ErrorResult(
                message=f"Invalid selector: {e}",
                code="CST_QUERY_PARSE_ERROR",
                details={"selector": selector},
            )
        except Exception as e:
            logger.exception("query_cst failed: %s", e)
            return ErrorResult(message=f"query_cst failed: {e}", code="CST_QUERY_ERROR")
