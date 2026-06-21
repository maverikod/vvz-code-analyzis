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


from pathlib import Path


from typing import Any, Dict, cast


from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


from ..core.exceptions import ValidationError
from .base_mcp_command import BaseMCPCommand


from .preview_config_defaults import get_preview_config_defaults
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
from .universal_file_preview.node_ref_params import normalize_optional_node_ref


from .universal_file_preview.preview_addressing import (
    check_preview_addressing,
    parse_error_from_focus,
    preview_source_is_parseable,
)
from .universal_file_preview.preview_pagination import apply_preview_pagination
from .universal_file_preview.response import build_envelope


from code_analysis.commands.universal_file_edit.format_group import check_lock
from code_analysis.commands.universal_file_edit.invalid_write_support import (
    mode_notice_text,
)


from .universal_file_preview.session import merge_edit_session_into_preview_params
from code_analysis.commands.preview_command_metadata import (
    get_universal_file_preview_metadata,
)

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
                    "description": (
                        "Drill-down node identifier from a prior preview response. "
                        "All marked-tree formats return and accept a positive integer "
                        "``short_id`` (internal TreeNodeUuid lives only in the ``.tree`` "
                        "MAP section). Legacy string forms (MAP UUID4, JSON Pointer, "
                        "markdown slug) are resolved to ``short_id`` before navigation. "
                        "Omit for file root."
                    ),
                    "oneOf": [
                        {
                            "type": "integer",
                            "minimum": 1,
                            "description": (
                                "Marked-tree short_id; canonical round-trip form."
                            ),
                        },
                        {
                            "type": "string",
                            "description": (
                                "Legacy alias resolved via MAP (UUID4, JSON Pointer, "
                                "markdown slug, or decimal short_id string)."
                            ),
                        },
                    ],
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
                        "Per-format source-line threshold. When the file has fewer "
                        "lines than this value, root preview returns annotated full "
                        "source on focus and every tree node in blocks. Default 200. "
                        "Set to 0 to disable (drilldown only)."
                    ),
                    "nullable": True,
                },
                "tree_id": {
                    "type": "string",
                    "description": "UUID of an existing in-memory TreeSession.",
                    "nullable": True,
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "UUID from universal_file_open. When set, preview uses the "
                        "edit session in-memory tree (or draft file for text format) "
                        "instead of reading unchanged content from disk."
                    ),
                    "nullable": True,
                },
                "max_chars": {
                    "type": "integer",
                    "minimum": 1,
                    "description": (
                        "Invalid-source fallback only: max characters per preview_chunk "
                        "page when the file failed structural parse (is_invalid). Ignored "
                        "when the file parses normally."
                    ),
                    "nullable": True,
                },
                "preview_offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "Invalid-source fallback only: character offset into serialized "
                        "invalid-source preview; use preview_next_offset from prior page. "
                        "Must be 0 for parseable files (use node_ref / selector instead)."
                    ),
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
            raise ValidationError(
                INPUT_ERROR_GLOB_IN_FILE_PATH,
                field="file_path",
            )

        node_ref = normalize_optional_node_ref(params.get("node_ref"))

        selector = params.get("selector")
        if isinstance(selector, str):
            if ":" not in selector and not selector.startswith("-"):
                raise ValidationError(
                    INPUT_ERROR_INVALID_SELECTOR_FORM,
                    field="selector",
                )
        elif isinstance(selector, list) and selector:
            if not (
                all(isinstance(x, int) for x in selector)
                or all(isinstance(x, str) for x in selector)
            ):
                raise ValidationError(
                    INPUT_ERROR_MIXED_SELECTOR_LIST,
                    field="selector",
                )
            if len(selector) != len(set(map(str, selector))):
                raise ValidationError(
                    INPUT_ERROR_DUPLICATE_SELECTOR_ENTRY,
                    field="selector",
                )

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
        session_id = params.get("session_id")

        preview_defaults = get_preview_config_defaults()
        max_chars = params.get("max_chars")
        if max_chars is None:
            max_chars = int(preview_defaults["preview_max_chars_default"])

        preview_offset = params.get("preview_offset")
        if preview_offset is None:
            preview_offset = 0

        return {
            "project_id": project_id,
            "file_path": file_path,
            "node_ref": node_ref,
            "selector": selector,
            "preview_lines": preview_lines,
            "value_preview_len": value_preview_len,
            "full_text_max_lines": full_text_max_lines,
            "tree_id": tree_id,
            "session_id": session_id,
            "max_chars": int(max_chars),
            "preview_offset": int(preview_offset),
        }

    @classmethod
    def metadata(cls: "type[UniversalFilePreviewCommand]") -> Dict[str, Any]:
        """Return extended AI/docs metadata for universal_file_preview.

        Returns:
            Metadata dict with description, parameters, examples, errors.
        """
        return cast(Dict[str, Any], get_universal_file_preview_metadata(cls))

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
            merged = merge_edit_session_into_preview_params(kwargs)
            if isinstance(merged, PreviewError):
                return ErrorResult(
                    message=merged.message,
                    code=cast(Any, merged.code),
                    details=merged.details or {},
                )
            kwargs = merged

            project_root = self._resolve_project_root(kwargs["project_id"])
            abs_file_path = kwargs.get("_preview_abs_path") or str(
                project_root / kwargs["file_path"]
            )

            # Lock check: refuse preview if file is locked by another session.
            caller_sid = str(kwargs.get("session_id") or "")
            lock_owner = check_lock(Path(abs_file_path), caller_sid)
            if lock_owner:
                return ErrorResult(
                    message=f"File is locked by edit session {lock_owner}",
                    code="FILE_LOCKED",
                    details={"lock_session_id": lock_owner},
                )

            dispatcher = HandlerDispatcher()
            handler_result = dispatcher.dispatch(kwargs["file_path"])
            if isinstance(handler_result, PreviewError):
                return ErrorResult(
                    message=handler_result.message,
                    code=cast(Any, handler_result.code),
                    details=handler_result.details or {},
                )
            handler = handler_result

            parseable = preview_source_is_parseable(Path(abs_file_path))
            addressing_err = check_preview_addressing(
                parseable=parseable,
                params=kwargs,
                file_path=kwargs["file_path"],
            )
            if addressing_err is not None:
                return ErrorResult(
                    message=addressing_err.message,
                    code=cast(Any, addressing_err.code),
                    details=addressing_err.details or {},
                )

            budget = PreviewBudget(
                preview_lines=int(kwargs["preview_lines"]),
                value_preview_len=int(kwargs["value_preview_len"]),
                full_text_max_lines=int(kwargs["full_text_max_lines"]),
                max_chars=int(kwargs["max_chars"]),
                preview_offset=int(kwargs["preview_offset"]),
            )
            nav_kwargs = dict(kwargs)
            nav_kwargs["file_path"] = abs_file_path
            nav_kwargs["project_root"] = project_root
            nav_kwargs["rel_file_path"] = kwargs["file_path"]
            # Thread caps through nav_kwargs so open_root receives budget even when
            # resolve_session returns session=None (plain preview, text edit session).
            nav_kwargs["preview_budget"] = budget
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
                else (
                    "caller_owned"
                    if kwargs.get("tree_id") or kwargs.get("session_id")
                    else "none"
                )
            )
            envelope = build_envelope(
                navigation_result,
                kwargs.get("selector"),
                session_origin,
            )
            focus_attrs = navigation_result.focus_node.attributes or {}
            if navigation_result.focus_node.is_invalid:
                paginated = apply_preview_pagination(
                    envelope,
                    offset=budget.preview_offset,
                    max_chars=budget.max_chars,
                )
                paginated["mode_notice"] = mode_notice_text(
                    True,
                    parse_error_from_focus(focus_attrs),
                )
                return SuccessResult(data=paginated)

            envelope["mode_notice"] = mode_notice_text(False)
            return SuccessResult(data=envelope)
        except Exception as exc:
            logger.error("universal_file_preview failed: %s", exc, exc_info=True)
            return ErrorResult(
                message=str(exc),
                code=cast(Any, "HANDLER_ERROR"),
            )
