"""
MCP command: get_file_lines

Return raw file lines in a range without parsing (no LibCST).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .line_command_cst_gate import (
    LINE_CMD_DISALLOWED_MSG,
    healthy_parse_blocks_line_ops,
)
from ..core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class GetFileLinesCommand(BaseMCPCommand):
    """Return raw file lines in a range without parsing."""

    name = "get_file_lines"
    version = "1.0.0"
    descr = "Return raw lines of a file in a range without parsing (for syntax errors or line-range view)"
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
                    "description": "Project ID (UUID4)",
                },
                "file_path": {
                    "type": "string",
                    "description": "File path relative to project root",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-based, inclusive)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (1-based, inclusive)",
                },
            },
            "required": ["project_id", "file_path", "start_line", "end_line"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        start_line: int,
        end_line: int,
        allow_healthy_line_ops: bool = False,
        **kwargs: Any,
    ) -> SuccessResult:
        try:
            if start_line > end_line:
                return ErrorResult(
                    message=f"Invalid range: start_line ({start_line}) > end_line ({end_line})",
                    code="INVALID_RANGE",
                    details={
                        "project_id": project_id,
                        "file_path": file_path,
                        "start_line": start_line,
                        "end_line": end_line,
                    },
                )
            if start_line < 1 or end_line < 1:
                return ErrorResult(
                    message="Line numbers must be >= 1 (1-based)",
                    code="INVALID_RANGE",
                    details={
                        "project_id": project_id,
                        "file_path": file_path,
                        "start_line": start_line,
                        "end_line": end_line,
                    },
                )

            database = self._open_database_from_config(auto_analyze=False)
            absolute_path = self._resolve_file_path_from_project(
                database, project_id, file_path
            )

            if not absolute_path.exists():
                return ErrorResult(
                    message=f"File not found: {absolute_path}",
                    code="FILE_NOT_FOUND",
                    details={
                        "project_id": project_id,
                        "file_path": file_path,
                        "resolved_path": str(absolute_path),
                    },
                )

            text = absolute_path.read_text(encoding="utf-8", errors="replace")
            config_data = self._get_raw_config()
            allow_on_healthy = config_data.get("code_analysis", {}).get(
                "allow_line_commands_on_healthy_files", False
            )
            if healthy_parse_blocks_line_ops(
                text,
                allow_healthy_line_ops=allow_healthy_line_ops,
                allow_line_commands_on_healthy_files=bool(allow_on_healthy),
            ):
                return ErrorResult(
                    message=LINE_CMD_DISALLOWED_MSG,
                    code="USE_CST_COMMANDS",
                    details={
                        "file_path": file_path,
                        "cst_commands": [
                            "cst_load_file",
                            "cst_modify_tree",
                            "compose_cst_module",
                        ],
                    },
                )
            all_lines = text.splitlines(keepends=False)
            total_lines = len(all_lines)

            if total_lines == 0:
                return SuccessResult(
                    data={
                        "success": True,
                        "file_path": file_path,
                        "start_line": 1,
                        "end_line": 0,
                        "lines": [],
                        "total_lines": 0,
                    }
                )

            # Clamp to actual file range (1-based inclusive)
            low = max(1, min(start_line, total_lines))
            high = max(1, min(end_line, total_lines))
            if low > high:
                low, high = high, low
            # 0-based slice
            lines = all_lines[low - 1 : high]

            return SuccessResult(
                data={
                    "success": True,
                    "file_path": file_path,
                    "start_line": low,
                    "end_line": high,
                    "lines": lines,
                    "total_lines": total_lines,
                }
            )

        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            logger.exception("get_file_lines failed: %s", e)
            return ErrorResult(
                message=f"get_file_lines failed: {e}",
                code="GET_FILE_LINES_ERROR",
            )
