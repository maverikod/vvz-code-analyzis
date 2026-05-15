"""
MCP command: universal_file_preview

Uniform structured preview of any project file node.
Read-only; never writes to files, database, or tree sessions
the command did not create.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations


import logging


from typing import Any, cast


from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


from .base_mcp_command import BaseMCPCommand


from .universal_file_preview.budget import PreviewBudget


from .universal_file_preview.dispatcher import HandlerDispatcher


from .universal_file_preview.errors import (
    INPUT_ERROR_DUPLICATE_SELECTOR_ENTRY,
    INPUT_ERROR_GLOB_IN_FILE_PATH,
    INPUT_ERROR_INVALID_SELECTOR_FORM,
    INPUT_ERROR_MIXED_SELECTOR_LIST,
    PreviewError,
)


from .universal_file_preview.navigation import navigate


from .universal_file_preview.response import build_envelope


_GLOB_CHARS = frozenset("*?[")


_PREVIEW_LINES_DEFAULT = 20


_VALUE_PREVIEW_LEN_DEFAULT = 120
_FULL_TEXT_MAX_LINES_DEFAULT = 200

_SCOPE_INVARIANTS: tuple[str, ...] = (
    "NO_WRITES: command never writes to files, database, or tree sessions"
    " it did not create",
    "NO_RAW_BYTES: response never contains raw file bytes; all output is"
    " structured JSON",
    "SINGLE_FILE: file_path is a single literal path; globs and wildcards"
    " are rejected as GLOB_IN_FILE_PATH",
    "NO_XML_HTML: no FileHandler is registered for .xml, .html, .htm;"
    " requests produce UNKNOWN_EXTENSION",
)


logger = logging.getLogger(__name__)


class UniversalFilePreviewCommand(BaseMCPCommand):
    """
    MCP command that returns a structured preview of any project file node.

    Supports .py, .pyi, .pyw (Python), .md, .txt, .rst, .adoc (text),
    .json (JSON), .jsonl, .ndjson (JSON Lines), .yaml, .yml (YAML).
    XML and HTML are out of scope.

    Attributes:
        name: Command name identifier.
        version: Command version string.
        descr: Human-readable command description.
        category: Command category.
        author: Author name.
        email: Author email.
        use_queue: Whether to use async queue for execution.
    """

    name = "universal_file_preview"

    version = "1.0.0"

    descr = "Uniform structured preview of any project file node"

    category = "preview"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @classmethod
    def get_schema(cls) -> dict[str, Any]:
        """Return JSON Schema for the command input parameters.

        Returns:
            JSON Schema dict describing accepted parameters.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID."},
                "file_path": {
                    "type": "string",
                    "description": "Project-relative path to one file. No globs.",
                },
                "node_ref": {
                    "type": "string",
                    "description": "StableIdentifier in file handler native "
                    "format. Omit for file root.",
                    "nullable": True,
                },
                "selector": {
                    "description": (
                        "Picks a subset of the focus node block set. "
                        "String (slice form: contains ':' or starts with '-'), "
                        "list[int] (explicit indices), or list[str] (block "
                        "identifiers). Omit to get first preview_lines blocks."
                    ),
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "integer"}},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "nullable": True,
                },
                "preview_lines": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Cap on blocks returned when selector is omitted.",
                    "nullable": True,
                },
                "value_preview_len": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Cap on inline scalar/name length.",
                    "nullable": True,
                },
                "full_text_max_lines": {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "Python handler: when the file has fewer lines than this "
                        "threshold, return the entire file as a single text block. "
                        "Default 200. Set to 0 to disable full-text fallback."
                    ),
                    "nullable": True,
                },
                "tree_id": {
                    "type": "string",
                    "description": "UUID of an existing in-memory TreeSession.",
                    "nullable": True,
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    def validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalise raw MCP call parameters.

        Args:
            params: Raw parameter dict from the MCP call.

        Returns:
            Normalised parameter dict with defaults applied.
        """
        params = super().validate_params(params)

        project_id = params["project_id"]
        file_path = params["file_path"]
        if any(c in file_path for c in _GLOB_CHARS):
            raise ValueError(INPUT_ERROR_GLOB_IN_FILE_PATH)

        node_ref = params.get("node_ref")

        selector = params.get("selector")
        if isinstance(selector, str):
            if ":" not in selector and not selector.startswith("-"):
                raise ValueError(INPUT_ERROR_INVALID_SELECTOR_FORM)
        elif isinstance(selector, list) and selector:
            if not (
                all(isinstance(x, int) for x in selector)
                or all(isinstance(x, str) for x in selector)
            ):
                raise ValueError(INPUT_ERROR_MIXED_SELECTOR_LIST)
            if len(selector) != len(set(map(str, selector))):
                raise ValueError(INPUT_ERROR_DUPLICATE_SELECTOR_ENTRY)

        preview_lines = params.get("preview_lines")
        if preview_lines is None:
            preview_lines = _PREVIEW_LINES_DEFAULT

        value_preview_len = params.get("value_preview_len")
        if value_preview_len is None:
            value_preview_len = _VALUE_PREVIEW_LEN_DEFAULT

        full_text_max_lines = params.get("full_text_max_lines")
        if full_text_max_lines is None:
            full_text_max_lines = _FULL_TEXT_MAX_LINES_DEFAULT

        tree_id = params.get("tree_id")

        return {
            "project_id": project_id,
            "file_path": file_path,
            "node_ref": node_ref,
            "selector": selector,
            "preview_lines": preview_lines,
            "value_preview_len": value_preview_len,
            "full_text_max_lines": full_text_max_lines,
            "tree_id": tree_id,
        }

    async def execute(self, **kwargs: Any) -> SuccessResult | ErrorResult:  # type: ignore[override]
        """Execute the preview command.

        Resolves the project-relative file_path to an absolute path using
        project_id before dispatching to the file handler.

        Args:
            **kwargs: Validated parameters from validate_params.

        Returns:
            SuccessResult with ResponseEnvelope data, or ErrorResult on failure.
        """
        try:
            project_root = self._resolve_project_root(kwargs["project_id"])
            abs_file_path = str(project_root / kwargs["file_path"])

            dispatcher = HandlerDispatcher()
            handler_result = dispatcher.dispatch(kwargs["file_path"])
            if isinstance(handler_result, PreviewError):
                return ErrorResult(
                    message=handler_result.message,
                    code=cast(Any, handler_result.code),
                    details=handler_result.details or {},
                )
            handler = handler_result

            budget = PreviewBudget(
                preview_lines=int(kwargs["preview_lines"]),
                value_preview_len=int(kwargs["value_preview_len"]),
                full_text_max_lines=int(kwargs["full_text_max_lines"]),
            )
            nav_kwargs = {**kwargs, "file_path": abs_file_path}
            navigation_result = navigate(handler, nav_kwargs, budget)
            if isinstance(navigation_result, PreviewError):
                return ErrorResult(
                    message=navigation_result.message,
                    code=cast(Any, navigation_result.code),
                    details=navigation_result.details or {},
                )
            session_origin = (
                "command_created"
                if navigation_result.tree_id is not None
                else ("caller_owned" if kwargs.get("tree_id") else "none")
            )
            envelope = build_envelope(
                navigation_result,
                kwargs.get("selector"),
                session_origin,
            )
            return SuccessResult(data=envelope)
        except Exception as exc:
            logger.error("universal_file_preview failed: %s", exc, exc_info=True)
            return ErrorResult(
                message=str(exc),
                code=cast(Any, "HANDLER_ERROR"),
            )
