"""
MCP command: universal_file_read

Registry-first file read: routes by extension to text, JSON, YAML, or Python
handlers before reading file content. Does not replace ``read_project_text_file``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple, Type, Union

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .get_file_lines_command import GetFileLinesCommand
from .registration import (
    MCP_FILE_MANAGEMENT_REGISTRY_HELP,
    REGISTRY_SCHEMA_DISCOVERY_SHORT,
)
from ..core.exceptions import ValidationError
from ..core.file_handlers.base import FileHandlerRequest, FileHandlerResult
from ..core.file_handlers.json_handler import JsonFileHandler
from ..core.file_handlers.registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_YAML,
    RegistryError,
    resolve_handler,
)
from ..core.file_handlers.text_handler import read_lines_range_ok
from ..core.file_handlers.yaml_handler import YamlFileHandler

logger = logging.getLogger(__name__)

_FULL_FILE_END_LINE = 10**9


def _normalize_line_range(
    start_line: Optional[int],
    end_line: Optional[int],
) -> Union[Tuple[int, int], ErrorResult]:
    """Default missing bounds to a full-file logical range (clamped later)."""
    if start_line is None and end_line is None:
        return (1, _FULL_FILE_END_LINE)
    if start_line is None or end_line is None:
        return ErrorResult(
            message="start_line and end_line must both be provided or both omitted",
            code="VALIDATION_ERROR",
            details={"start_line": start_line, "end_line": end_line},
        )
    return (start_line, end_line)


def _success_from_handler(fr: FileHandlerResult) -> SuccessResult:
    data: Dict[str, Any] = {
        "success": True,
        "handler_id": fr.handler_id,
        "operation": fr.operation,
        "file_path": fr.file_path,
        "project_id": fr.project_id,
    }
    data.update(fr.data)
    return SuccessResult(data=data)


def _error_from_handler(fr: FileHandlerResult) -> ErrorResult:
    return ErrorResult(
        message=fr.message or fr.code,
        code=fr.code or "VALIDATION_FAILED",
        details=fr.details
        or {
            "file_path": fr.file_path,
            "handler_id": fr.handler_id,
            "operation": fr.operation,
        },
    )


class UniversalFileReadCommand(BaseMCPCommand):
    """Read project files via handler registry (extension routing before I/O)."""

    name = "universal_file_read"
    version = "1.0.0"
    descr = (
        "Read a project file using the universal handler registry. "
        "Extensions .toml and unknown mapped types fail with UNSUPPORTED_FILE_EXTENSION "
        "before file access." + " " + MCP_FILE_MANAGEMENT_REGISTRY_HELP
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "title": "universal_file_read",
            "description": (
                "Registry-first read: .md/.txt/.rst/.adoc as text lines; .json structured tree; "
                ".yaml/.yml structured document; .py/.pyi/.pyw via get_file_lines (line view). "
                ".toml and unregistered extensions return UNSUPPORTED_FILE_EXTENSION before "
                "reading the file. start_line/end_line are optional; when omitted, text and "
                "Python paths read the whole file (clamped). Structured JSON/YAML reads ignore "
                "line bounds. " + REGISTRY_SCHEMA_DISCOVERY_SHORT
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Single path relative to project root (literal; no ``*?[]`` globs — "
                        "use ``list_project_files`` with ``file_pattern`` to discover paths)."
                    ),
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Optional. For text and Python line views; must be paired with end_line."
                    ),
                },
                "end_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Optional. For text and Python line views; must be paired with start_line."
                    ),
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileReadCommand"]) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "detailed_description": cls.descr,
            "registry_discovery_python": (
                "code_analysis.core.file_handlers.registry — get_handler_schema, "
                "list_handler_mappings, HANDLER_IDS"
            ),
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult:
        try:
            try:
                handler_id = resolve_handler(file_path, "read")
            except RegistryError as e:
                return ErrorResult(
                    message=str(e),
                    code=e.code,
                    details=e.details,
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
                        "handler_id": handler_id,
                        "operation": "read",
                        "resolved_path": str(absolute_path),
                    },
                )

            if handler_id == HANDLER_JSON:
                req = FileHandlerRequest(
                    project_id=project_id,
                    file_path=file_path,
                    handler_id=handler_id,
                    operation="read",
                    extra={"absolute_path": absolute_path},
                )
                fr = JsonFileHandler().read(req)
                if not fr.success:
                    return _error_from_handler(fr)
                return _success_from_handler(fr)

            if handler_id == HANDLER_YAML:
                req = FileHandlerRequest(
                    project_id=project_id,
                    file_path=file_path,
                    handler_id=handler_id,
                    operation="read",
                    extra={"absolute_path": absolute_path},
                )
                fr = YamlFileHandler().read(req)
                if not fr.success:
                    return _error_from_handler(fr)
                return _success_from_handler(fr)

            bounds = _normalize_line_range(start_line, end_line)
            if isinstance(bounds, ErrorResult):
                return bounds
            sl, el = bounds

            if handler_id == HANDLER_TEXT:
                payload = read_lines_range_ok(absolute_path, sl, el)
                if not payload.get("success"):
                    return ErrorResult(
                        message=str(payload.get("message", "Invalid range")),
                        code=str(payload.get("code", "INVALID_RANGE")),
                        details={
                            "project_id": project_id,
                            "file_path": file_path,
                            "handler_id": HANDLER_TEXT,
                            "operation": "read",
                            "start_line": sl,
                            "end_line": el,
                        },
                    )
                return SuccessResult(
                    data={
                        "success": True,
                        "handler_id": HANDLER_TEXT,
                        "operation": "read",
                        "file_path": file_path,
                        "project_id": project_id,
                        "start_line": payload["start_line"],
                        "end_line": payload["end_line"],
                        "lines": payload["lines"],
                        "total_lines": payload["total_lines"],
                    }
                )

            if handler_id == HANDLER_PYTHON:
                routed = GetFileLinesCommand()
                res = await routed.execute(
                    project_id=project_id,
                    file_path=file_path,
                    start_line=sl,
                    end_line=el,
                    allow_healthy_line_ops=True,
                )
                if isinstance(res, ErrorResult):
                    det = dict(res.details or {})
                    det.setdefault("handler_id", HANDLER_PYTHON)
                    det.setdefault("operation", "read")
                    return ErrorResult(
                        message=res.message,
                        code=res.code or "ERROR",
                        details=det,
                    )
                data = dict(res.data or {})
                data["success"] = True
                data["handler_id"] = HANDLER_PYTHON
                data["operation"] = "read"
                data["project_id"] = project_id
                data["file_path"] = file_path
                return SuccessResult(data=data)

            return ErrorResult(
                message=f"Unhandled handler_id after registry resolve: {handler_id!r}",
                code="INTERNAL_ERROR",
                details={
                    "project_id": project_id,
                    "file_path": file_path,
                    "handler_id": handler_id,
                    "operation": "read",
                },
            )

        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            logger.exception("universal_file_read failed: %s", e)
            return ErrorResult(
                message=f"universal_file_read failed: {e}",
                code="UNIVERSAL_FILE_READ_ERROR",
            )
