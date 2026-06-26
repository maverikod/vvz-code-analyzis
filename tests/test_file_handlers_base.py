"""
Minimal tests for :mod:`code_analysis.core.file_handlers.base` contract.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from code_analysis.core.file_handlers.base import (
    BaseFileHandler,
    FileHandlerRequest,
    FileHandlerResult,
    UNSUPPORTED_OPERATION,
    VALIDATION_FAILED,
    validate_before_side_effects,
)
from code_analysis.core.file_handlers.registry import HANDLER_TEXT, get_handler_schema


class _MinimalHandler(BaseFileHandler):
    """Represent MinimalHandler."""

    @property
    def handler_id(self) -> str:
        """Return handler id."""
        return HANDLER_TEXT

    def json_schema_for(self, operation: str) -> dict:
        """Return json schema for."""
        return dict(get_handler_schema(HANDLER_TEXT, operation))

    def read(self, request: FileHandlerRequest) -> FileHandlerResult:
        """Return read."""
        raise NotImplementedError

    def save(self, request: FileHandlerRequest) -> FileHandlerResult:
        """Return save."""
        raise NotImplementedError

    def replace(self, request: FileHandlerRequest) -> FileHandlerResult:
        """Return replace."""
        raise NotImplementedError

    def delete(self, request: FileHandlerRequest) -> FileHandlerResult:
        """Return delete."""
        raise NotImplementedError


def test_validate_before_side_effects_empty_project() -> None:
    """Verify test validate before side effects empty project."""
    req = FileHandlerRequest(
        project_id="   ",
        file_path="x.md",
        handler_id="text",
        operation="save",
    )
    out = validate_before_side_effects(req)
    assert out is not None
    assert out.success is False
    assert out.code == VALIDATION_FAILED
    assert out.details["file_path"] == "x.md"


def test_operation_availability_all_four() -> None:
    """Verify test operation availability all four."""
    h = _MinimalHandler()
    avail = h.operation_availability()
    assert set(avail.keys()) == {"delete", "read", "replace", "save"}
    assert all(avail[k] for k in avail)


def test_registration_readiness_uses_json_schema_all_ops() -> None:
    """Verify test registration readiness uses json schema all ops."""
    h = _MinimalHandler()
    r = h.registration_readiness()
    assert all(entry["supported"] for entry in r.values())
    assert all(entry["schema_ok"] and entry["ready"] for entry in r.values())


def test_mutating_precheck_rejects_unknown_operation() -> None:
    """Verify test mutating precheck rejects unknown operation."""
    h = _MinimalHandler()
    req = FileHandlerRequest(
        project_id="p",
        file_path="a.md",
        handler_id="text",
        operation="warp",
    )
    failed = h.mutating_precheck(req)
    assert failed is not None
    assert failed.code == UNSUPPORTED_OPERATION
