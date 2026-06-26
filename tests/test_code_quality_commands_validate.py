"""Tests for format_code, lint_code, and type_check_code parameter validation."""

from __future__ import annotations

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.format_code_command import FormatCodeCommand
from code_analysis.commands.lint_code_command import LintCodeCommand
from code_analysis.commands.type_check_code_command import TypeCheckCodeCommand
from code_analysis.core.exceptions import ValidationError


@pytest.fixture
def format_cmd() -> FormatCodeCommand:
    """Return format cmd."""
    return FormatCodeCommand()


@pytest.fixture
def lint_cmd() -> LintCodeCommand:
    """Return lint cmd."""
    return LintCodeCommand()


@pytest.fixture
def type_check_cmd() -> TypeCheckCodeCommand:
    """Return type check cmd."""
    return TypeCheckCodeCommand()


def test_format_code_validate_params_accepts_minimal(
    format_cmd: FormatCodeCommand,
) -> None:
    """Verify test format code validate params accepts minimal."""
    out = format_cmd.validate_params({"file_path": "hello.py"})
    assert out["file_path"] == "hello.py"


def test_format_code_validate_params_rejects_unknown_param(
    format_cmd: FormatCodeCommand,
) -> None:
    """Verify test format code validate params rejects unknown param."""
    with pytest.raises(ValidationError, match="unknown parameter"):
        format_cmd.validate_params({"file_path": "hello.py", "__unknown_param__": True})


def test_format_code_validate_params_rejects_wrong_type_file_path(
    format_cmd: FormatCodeCommand,
) -> None:
    """Verify test format code validate params rejects wrong type file path."""
    with pytest.raises(ValidationError, match="file_path") as exc_info:
        format_cmd.validate_params({"file_path": 123})
    assert exc_info.value.field == "file_path"


def test_format_code_validate_params_rejects_wrong_type_project_id(
    format_cmd: FormatCodeCommand,
) -> None:
    """Verify test format code validate params rejects wrong type project id."""
    with pytest.raises(ValidationError, match="project_id") as exc_info:
        format_cmd.validate_params({"file_path": "hello.py", "project_id": 123})
    assert exc_info.value.field == "project_id"


@pytest.mark.asyncio
async def test_format_code_execute_rejects_wrong_type_at_entry(
    format_cmd: FormatCodeCommand,
) -> None:
    """Verify test format code execute rejects wrong type at entry."""
    result = await format_cmd.execute(file_path=123)  # type: ignore[arg-type]
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "file_path" in result.message


def test_lint_code_validate_params_accepts_ignore_list(
    lint_cmd: LintCodeCommand,
) -> None:
    """Verify test lint code validate params accepts ignore list."""
    out = lint_cmd.validate_params(
        {"file_path": "hello.py", "ignore": ["E501", "W503"]}
    )
    assert out["ignore"] == ["E501", "W503"]


def test_lint_code_validate_params_rejects_wrong_type_ignore(
    lint_cmd: LintCodeCommand,
) -> None:
    """Verify test lint code validate params rejects wrong type ignore."""
    with pytest.raises(ValidationError, match="ignore") as exc_info:
        lint_cmd.validate_params({"file_path": "hello.py", "ignore": "E501"})
    assert exc_info.value.field == "ignore"


def test_lint_code_validate_params_rejects_unknown_param(
    lint_cmd: LintCodeCommand,
) -> None:
    """Verify test lint code validate params rejects unknown param."""
    with pytest.raises(ValidationError, match="unknown parameter"):
        lint_cmd.validate_params({"file_path": "hello.py", "__unknown_param__": 1})


@pytest.mark.asyncio
async def test_lint_code_execute_rejects_wrong_type_ignore_at_entry(
    lint_cmd: LintCodeCommand,
) -> None:
    """Verify test lint code execute rejects wrong type ignore at entry."""
    result = await lint_cmd.execute(file_path="hello.py", ignore="E501")  # type: ignore[arg-type]
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "ignore" in result.message


def test_type_check_code_validate_params_accepts_ignore_errors(
    type_check_cmd: TypeCheckCodeCommand,
) -> None:
    """Verify test type check code validate params accepts ignore errors."""
    out = type_check_cmd.validate_params(
        {"file_path": "hello.py", "ignore_errors": True}
    )
    assert out["ignore_errors"] is True


def test_type_check_code_validate_params_rejects_wrong_type_ignore_errors(
    type_check_cmd: TypeCheckCodeCommand,
) -> None:
    """Verify test type check code validate params rejects wrong type ignore errors."""
    with pytest.raises(ValidationError, match="ignore_errors") as exc_info:
        type_check_cmd.validate_params(
            {"file_path": "hello.py", "ignore_errors": "yes"}
        )
    assert exc_info.value.field == "ignore_errors"


def test_type_check_code_validate_params_rejects_unknown_param(
    type_check_cmd: TypeCheckCodeCommand,
) -> None:
    """Verify test type check code validate params rejects unknown param."""
    with pytest.raises(ValidationError, match="unknown parameter"):
        type_check_cmd.validate_params(
            {"file_path": "hello.py", "__unknown_param__": "x"}
        )


@pytest.mark.asyncio
async def test_type_check_code_execute_rejects_wrong_type_ignore_errors_at_entry(
    type_check_cmd: TypeCheckCodeCommand,
) -> None:
    """Verify test type check code execute rejects wrong type ignore errors at entry."""
    result = await type_check_cmd.execute(
        file_path="hello.py",
        ignore_errors="yes",  # type: ignore[arg-type]
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "ignore_errors" in result.message
