"""
MCP command: read_project_text_file

Read raw text file lines in a range for non-code files. Python paths are
delegated to ``get_file_lines`` (line-based CST path) automatically; other
program source suffixes remain rejected — see ``project_text_file_guard``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Type

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .get_file_lines_command import GetFileLinesCommand
from .project_text_file_guard import (
    is_python_text_path,
    reject_if_non_python_code_text_path,
)
from ..core.constants import DEFAULT_READ_PROJECT_TEXT_JSON_STRUCTURED_MAX_BYTES
from ..core.exceptions import ValidationError
from ..core.file_lock import file_lock
from ..core.json_tree.tree_builder import load_file_to_tree

logger = logging.getLogger(__name__)


def _resolved_json_structured_max_bytes(config_data: Dict[str, Any]) -> int:
    """Byte threshold for structured .json via read_project_text_file; config or default."""
    ca = config_data.get("code_analysis") or {}
    v = ca.get("read_project_text_json_structured_max_bytes")
    if v is None:
        return DEFAULT_READ_PROJECT_TEXT_JSON_STRUCTURED_MAX_BYTES
    if isinstance(v, bool) or not isinstance(v, int):
        return DEFAULT_READ_PROJECT_TEXT_JSON_STRUCTURED_MAX_BYTES
    if v < 1:
        return DEFAULT_READ_PROJECT_TEXT_JSON_STRUCTURED_MAX_BYTES
    return v


def _should_return_structured_json(path: Path, config_data: Dict[str, Any]) -> bool:
    """True when .json and on-disk size is within structured-read threshold."""
    if path.suffix.lower() != ".json":
        return False
    max_bytes = _resolved_json_structured_max_bytes(config_data)
    try:
        size = path.stat().st_size
    except OSError:
        return False
    return size <= max_bytes


class ReadProjectTextFileCommand(BaseMCPCommand):
    """Return raw lines in a range; Python paths route to get_file_lines automatically."""

    name = "read_project_text_file"
    version = "1.0.0"
    descr = (
        "Plain text and configs: reads raw lines. Python (.py, .pyi, …) is handled automatically "
        "via the same line-based path as get_file_lines (not raw-text rejection). "
        "Other program source suffixes are still forbidden."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "title": "read_project_text_file",
            "description": (
                "Read raw text lines from a project file. **Python paths** (.py, .pyi, …) are "
                "automatically routed to the same behavior as `get_file_lines` (line-based read; "
                "healthy Python succeeds without USE_CST_COMMANDS). Other blocked program-source "
                "suffixes return CODE_FILE_FORBIDDEN. Non-code files: docs and plain configs "
                "(README, .md, .json, .toml). For .json within the configured byte threshold, "
                "the response matches json_load_file (structured tree); larger .json files use "
                "raw lines. Line range is 1-based inclusive; clamped to file. Structured .json "
                "responses use the full document (line range ignored)."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID (from create_project or list_projects). "
                        "Must exist in the database."
                    ),
                    "examples": ["550e8400-e29b-41d4-a716-446655440000"],
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path relative to project root. Python (.py, .pyi, …) is routed to "
                        "get_file_lines automatically. Other program-source suffixes (e.g. .go, .rs) "
                        "are rejected (CODE_FILE_FORBIDDEN)."
                    ),
                    "examples": ["README.md", "docs/config.json", "src/module.py"],
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-based, inclusive)",
                    "minimum": 1,
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (1-based, inclusive)",
                    "minimum": 1,
                },
            },
            "required": ["project_id", "file_path", "start_line", "end_line"],
            "additionalProperties": False,
            "examples": [
                {
                    "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    "file_path": "README.md",
                    "start_line": 1,
                    "end_line": 20,
                },
            ],
        }

    @classmethod
    def metadata(cls: Type["ReadProjectTextFileCommand"]) -> Dict[str, Any]:
        """Structured discovery/help; JSON parameters remain authoritative in get_schema()."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "For **non-code** paths: reads raw lines without parsing. For **Python** paths "
                "(.py, .pyi, .pyw, .pyx, .pxd, .pxi), the implementation delegates to `get_file_lines` "
                "with internal routing so healthy files return lines (same response shape as "
                "get_file_lines). Other program-source suffixes are still rejected.\n\n"
                "Line numbers are 1-based inclusive. The range is clamped to the file; the response "
                "includes the actual start_line/end_line after clamping and total_lines."
            ),
            "parameters": {
                "project_id": {
                    "description": "Registered project UUID.",
                    "required": True,
                },
                "file_path": {
                    "description": (
                        "Path relative to project root. Python → auto `get_file_lines`; other "
                        "blocked source suffixes → error."
                    ),
                    "required": True,
                },
                "start_line": {
                    "description": "Start line (1-based, inclusive).",
                    "required": True,
                },
                "end_line": {
                    "description": "End line (1-based, inclusive).",
                    "required": True,
                },
            },
            "usage_examples": [
                {
                    "description": "First 20 lines of README.md",
                    "params": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "README.md",
                        "start_line": 1,
                        "end_line": 20,
                    },
                },
                {
                    "description": "Python file (routed to get_file_lines; same response shape)",
                    "params": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "pkg/mod.py",
                        "start_line": 1,
                        "end_line": 50,
                    },
                },
            ],
            "error_codes": [
                "CODE_FILE_FORBIDDEN",
                "INVALID_RANGE",
                "FILE_NOT_FOUND",
                "INVALID_JSON",
                "VALIDATION_ERROR",
                "READ_PROJECT_TEXT_FILE_ERROR",
            ],
            "error_codes_note": (
                "CODE_FILE_FORBIDDEN: non-Python program source — use the appropriate workflow. "
                "Python paths are routed to get_file_lines (see command description)."
            ),
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        start_line: int,
        end_line: int,
        **kwargs: Any,
    ) -> SuccessResult:
        try:
            blocked = reject_if_non_python_code_text_path(file_path)
            if blocked is not None:
                return blocked

            if is_python_text_path(file_path):
                routed = GetFileLinesCommand()
                return await routed.execute(
                    project_id=project_id,
                    file_path=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    allow_healthy_line_ops=True,
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

            if _should_return_structured_json(absolute_path, self._get_raw_config()):
                try:
                    with file_lock(absolute_path):
                        tree = load_file_to_tree(str(absolute_path))
                except ValueError as e:
                    return ErrorResult(
                        message=str(e),
                        code="INVALID_JSON",
                        details={
                            "project_id": project_id,
                            "file_path": file_path,
                            "error": str(e),
                        },
                    )
                nodes = [m.to_dict() for m in tree.metadata_map.values()]
                return SuccessResult(
                    data={
                        "success": True,
                        "tree_id": tree.tree_id,
                        "file_path": tree.file_path,
                        "root_node_id": tree.root_node_id,
                        "nodes": nodes,
                        "total_nodes": len(nodes),
                    }
                )

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

            text = absolute_path.read_text(encoding="utf-8", errors="replace")
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

            # Clamp to actual file range (1-based inclusive), same as get_file_lines
            low = max(1, min(start_line, total_lines))
            high = max(1, min(end_line, total_lines))
            if low > high:
                low, high = high, low
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
            logger.exception("read_project_text_file failed: %s", e)
            return ErrorResult(
                message=f"read_project_text_file failed: {e}",
                code="READ_PROJECT_TEXT_FILE_ERROR",
            )
