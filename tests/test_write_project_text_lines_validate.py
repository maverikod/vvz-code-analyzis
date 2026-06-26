"""Tests for write_project_text_lines parameter bounds validation."""

from __future__ import annotations

import uuid

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult

from code_analysis.commands.write_project_text_lines_command import (
    WriteProjectTextLinesCommand,
)
from code_analysis.core.exceptions import ValidationError


@pytest.fixture
def cmd() -> WriteProjectTextLinesCommand:
    """Return cmd."""
    return WriteProjectTextLinesCommand()


@pytest.fixture
def base_params() -> dict[str, object]:
    """Return base params."""
    return {
        "project_id": str(uuid.uuid4()),
        "file_path": "notes.txt",
        "start_line": 1,
        "end_line": 1,
        "new_lines": ["hello"],
    }


def test_validate_params_accepts_lines_in_range(
    cmd: WriteProjectTextLinesCommand,
    base_params: dict[str, object],
) -> None:
    """Verify test validate params accepts lines in range."""
    out = cmd.validate_params(dict(base_params))
    assert out["start_line"] == 1
    assert out["end_line"] == 1


@pytest.mark.parametrize("start_line", [0, -1])
def test_validate_params_rejects_start_line_out_of_range(
    cmd: WriteProjectTextLinesCommand,
    base_params: dict[str, object],
    start_line: int,
) -> None:
    """Verify test validate params rejects start line out of range."""
    params = {**base_params, "start_line": start_line}
    with pytest.raises(ValidationError, match="start_line") as exc_info:
        cmd.validate_params(params)
    assert exc_info.value.field == "start_line"


@pytest.mark.parametrize("end_line", [0, -5])
def test_validate_params_rejects_end_line_out_of_range(
    cmd: WriteProjectTextLinesCommand,
    base_params: dict[str, object],
    end_line: int,
) -> None:
    """Verify test validate params rejects end line out of range."""
    params = {**base_params, "end_line": end_line}
    with pytest.raises(ValidationError, match="end_line") as exc_info:
        cmd.validate_params(params)
    assert exc_info.value.field == "end_line"


@pytest.mark.asyncio
async def test_execute_rejects_start_line_out_of_range_at_entry(
    cmd: WriteProjectTextLinesCommand,
    base_params: dict[str, object],
) -> None:
    """Verify test execute rejects start line out of range at entry."""
    result = await cmd.execute(**{**base_params, "start_line": 0})
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "start_line" in result.message
