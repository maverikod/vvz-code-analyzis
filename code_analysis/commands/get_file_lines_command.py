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
from .base_mcp_command_resolve_path import resolve_under_project_root
from .line_command_cst_gate import (
    LINE_CMD_DISALLOWED_MSG,
    healthy_parse_blocks_line_ops,
)
from ..core.exceptions import ValidationError
from ..core.file_handlers.text_ranges import validate_range_against_length

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
        """Return the command input schema."""
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
                "allow_healthy_line_ops": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, allow line reads on Python files with a healthy "
                        "CST parse. Used when routing from read_project_text_file; "
                        "default false for direct get_file_lines calls."
                    ),
                },
            },
            "required": ["project_id", "file_path", "start_line", "end_line"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["GetFileLinesCommand"]) -> Dict[str, Any]:
        """Return metadata for raw file line-range reads."""
        from .command_metadata_helpers import (
            build_command_metadata,
            parameters_from_schema,
            project_file_error_cases,
            simple_success_return,
        )

        return build_command_metadata(
            cls,
            detailed_description=cls.descr,
            parameters=parameters_from_schema(cls.get_schema()),
            usage_examples=[
                {
                    "description": "Read lines when CST parse fails",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "broken.py",
                        "start_line": 1,
                        "end_line": 40,
                    },
                    "explanation": "Raw lines without LibCST; use for syntax-error recovery.",
                },
            ],
            error_cases={
                **project_file_error_cases(),
                "INVALID_RANGE": {
                    "description": "start_line > end_line or < 1.",
                },
            },
            return_value=simple_success_return(
                data_fields={"lines": "List of line strings"},
            ),
            best_practices=[
                "Prefer cst_load_file when the file parses cleanly.",
                "For Python with healthy parse, routing may still use this for line view.",
            ],
        )

    async def execute(
        self,
        project_id: str,
        file_path: str,
        start_line: int,
        end_line: int,
        allow_healthy_line_ops: bool = False,
        **kwargs: Any,
    ) -> SuccessResult:
        """Read an inclusive line range after project and CST-gate validation."""
        try:
            params: Dict[str, Any] = {
                "project_id": project_id,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "allow_healthy_line_ops": allow_healthy_line_ops,
            }
            params.update(kwargs)
            try:
                params = self.validate_params(params)
            except ValidationError as e:
                return ErrorResult(
                    message=str(e),
                    code="VALIDATION_ERROR",
                    details=getattr(e, "details", None)
                    or {"field": getattr(e, "field", None)},
                )
            project_id = params["project_id"]
            file_path = params["file_path"]
            start_line = params["start_line"]
            end_line = params["end_line"]
            allow_healthy_line_ops = bool(params.get("allow_healthy_line_ops", False))

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

            project_root = self._resolve_project_root(project_id)
            try:
                absolute_path = resolve_under_project_root(
                    project_root, file_path, require_exists=False
                )
            except ValidationError as e:
                return ErrorResult(
                    message=str(e),
                    code="VALIDATION_ERROR",
                    details=getattr(e, "details", None)
                    or {"field": getattr(e, "field", None)},
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
                file_path=file_path,
            ):
                return ErrorResult(
                    message=LINE_CMD_DISALLOWED_MSG,
                    code="USE_CST_COMMANDS",
                    details={
                        "file_path": file_path,
                        "cst_commands": [
                            "cst_load_file",
                            "cst_modify_tree",
                            "cst_modify_tree",
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

            try:
                validate_range_against_length(
                    start_line, end_line, total_lines, strict=True
                )
            except ValueError as e:
                return ErrorResult(
                    message=str(e),
                    code="INVALID_RANGE",
                    details={
                        "project_id": project_id,
                        "file_path": file_path,
                        "start_line": start_line,
                        "end_line": end_line,
                        "total_lines": total_lines,
                    },
                )
            lines = all_lines[start_line - 1 : end_line]
            low = start_line
            high = end_line

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
