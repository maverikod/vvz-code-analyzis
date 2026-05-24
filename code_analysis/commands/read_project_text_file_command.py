"""
MCP command: read_project_text_file

Compatibility wrapper over :class:`UniversalFileReadCommand` for registry-first
reads. Non-Python program sources are rejected via ``project_text_file_guard``
(``CODE_FILE_FORBIDDEN``). Python paths registered in the handler map delegate to
the same line-based flow as ``get_file_lines``; other Python-ecosystem suffixes
(``.pyx``, ``.pxd``, ``.pxi``) fall back to ``GetFileLinesCommand`` when the
registry has no mapping yet.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Type, Union

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .get_file_lines_command import GetFileLinesCommand
from .project_text_file_guard import (
    is_python_text_path,
    reject_if_non_python_code_text_path,
)
from .registration import (
    MCP_FILE_MANAGEMENT_REGISTRY_HELP,
    REGISTRY_SCHEMA_DISCOVERY_SHORT,
)
from .universal_file_read_command import UniversalFileReadCommand
from ..core.exceptions import ValidationError
from ..core.file_handlers.registry import HANDLER_PYTHON

logger = logging.getLogger(__name__)


class ReadProjectTextFileCommand(BaseMCPCommand):
    """Delegate reads to universal_file_read; keep legacy guard and Python fallbacks."""

    name = "read_project_text_file"
    version = "1.0.0"
    descr = (
        "Plain text and configs: reads via the universal handler registry (see "
        "`universal_file_read`). Python (``.py``, ``.pyi``, ``.pyw``) uses the same "
        "line-based path as `get_file_lines`. Other program source suffixes are "
        "forbidden." + " " + MCP_FILE_MANAGEMENT_REGISTRY_HELP
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
                "Read lines or structured content from a project file. Routes through "
                "`universal_file_read` (handler registry). **Python paths** "
                "(``.py``, ``.pyi``, ``.pyw``) use the same behavior as `get_file_lines`. "
                "Other blocked program-source suffixes return CODE_FILE_FORBIDDEN. "
                "``.json`` / ``.yaml`` use structured handlers (line ranges ignored for those). "
                "Success payloads include ``handler_id`` when returned by the universal read "
                "path. Line range is 1-based inclusive for text and Python line views; "
                "clamped to the file. " + REGISTRY_SCHEMA_DISCOVERY_SHORT
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
                        "Single literal path relative to project root (no ``*?[]`` globs). "
                        "Registry resolves the handler. Known non-Python source suffixes "
                        "(e.g. ``.go``, ``.rs``) are rejected (CODE_FILE_FORBIDDEN) before routing."
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
                "Delegates to **`universal_file_read`** for registry-based routing "
                "(text, JSON, YAML, Python). **Non-Python program sources** are rejected "
                "first with CODE_FILE_FORBIDDEN. Responses include **`handler_id`** and "
                "**`operation`** where the universal command supplies them.\n\n"
                "Line numbers are 1-based inclusive for text and Python line views."
            ),
            "parameters": {
                "project_id": {
                    "description": "Registered project UUID.",
                    "required": True,
                },
                "file_path": {
                    "description": (
                        "Path relative to project root (registry + guard). "
                        "Python → line read; blocked code suffixes → error."
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
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "README.md",
                        "start_line": 1,
                        "end_line": 20,
                    },
                    "explanation": "Delegates to universal_file_read for text.",
                },
                {
                    "description": "Python file (line read; handler_id=python)",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_path": "pkg/mod.py",
                        "start_line": 1,
                        "end_line": 50,
                    },
                    "explanation": "Blocked program sources return CODE_FILE_FORBIDDEN.",
                },
            ],
            "return_value": {
                "success": {
                    "description": "Lines returned from the routed handler.",
                    "data": {
                        "lines": "List of strings",
                        "handler_id": "text | python | …",
                    },
                    "example": {
                        "success": True,
                        "handler_id": "text",
                        "lines": ["# Hi"],
                    },
                },
                "error": {
                    "description": "Validation or routing failure.",
                    "code": "CODE_FILE_FORBIDDEN | FILE_NOT_FOUND | …",
                },
            },
            "error_cases": {
                "CODE_FILE_FORBIDDEN": {
                    "description": "Path is a blocked program-source suffix.",
                    "solution": "Use CST commands for Python sources.",
                },
                "FILE_NOT_FOUND": {
                    "description": "Path not found under project root.",
                    "solution": "Confirm path with list_project_files.",
                },
            },
            "best_practices": [
                "Prefer universal_file_read for new integrations.",
                "Use project-relative paths from list_projects root.",
            ],
            "error_codes": [
                "CODE_FILE_FORBIDDEN",
                "INVALID_RANGE",
                "FILE_NOT_FOUND",
                "VALIDATION_ERROR",
                "READ_PROJECT_TEXT_FILE_ERROR",
                "UNSUPPORTED_FILE_EXTENSION",
                "validation_failed",
            ],
            "error_codes_note": (
                "CODE_FILE_FORBIDDEN: non-Python program source. Invalid JSON under the "
                "JSON handler may return validation_failed (from the handler). "
                "Unknown / unmapped extensions return UNSUPPORTED_FILE_EXTENSION."
            ),
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Reject ``start_line`` and ``end_line`` outside schema min/max after schema validation."""
        params = super().validate_params(params)
        schema = self.get_schema()
        props = schema.get("properties") or {}
        for key in ("start_line", "end_line"):
            if key not in params or params[key] is None:
                continue
            value = params[key]
            prop = props.get(key) or {}
            minimum = prop.get("minimum")
            maximum = prop.get("maximum")
            if minimum is not None and value < minimum:
                raise ValidationError(
                    f"{self.name}: parameter {key!r} must be >= {minimum}, got {value!r}",
                    field=key,
                    details={"minimum": minimum, "maximum": maximum},
                )
            if maximum is not None and value > maximum:
                raise ValidationError(
                    f"{self.name}: parameter {key!r} must be <= {maximum}, got {value!r}",
                    field=key,
                    details={"minimum": minimum, "maximum": maximum},
                )
        return params

    async def execute(
        self,
        project_id: str,
        file_path: str,
        start_line: int,
        end_line: int,
        **kwargs: Any,
    ) -> Union[SuccessResult, ErrorResult]:
        try:
            params: Dict[str, Any] = {
                "project_id": project_id,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
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

            blocked = reject_if_non_python_code_text_path(file_path)
            if blocked is not None:
                return blocked

            inner = UniversalFileReadCommand()
            result = await inner.execute(
                project_id=project_id,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
            )

            if (
                isinstance(result, ErrorResult)
                and result.code == "UNSUPPORTED_FILE_EXTENSION"
            ):
                if is_python_text_path(file_path):
                    routed = GetFileLinesCommand()
                    py_res = await routed.execute(
                        project_id=project_id,
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        allow_healthy_line_ops=True,
                    )
                    if isinstance(py_res, ErrorResult):
                        det = dict(py_res.details or {})
                        det.setdefault("handler_id", HANDLER_PYTHON)
                        det.setdefault("operation", "read")
                        return ErrorResult(
                            message=py_res.message,
                            code=py_res.code or "ERROR",
                            details=det,
                        )
                    data = dict(py_res.data or {})
                    data["success"] = True
                    data["handler_id"] = HANDLER_PYTHON
                    data["operation"] = "read"
                    data["project_id"] = project_id
                    data["file_path"] = file_path
                    return SuccessResult(data=data)

            return result

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
