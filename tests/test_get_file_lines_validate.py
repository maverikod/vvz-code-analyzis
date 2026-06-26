"""Tests for get_file_lines range validation (reject OOB, no clamp)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.get_file_lines_command import GetFileLinesCommand

_PID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
async def test_get_file_lines_rejects_range_beyond_file(tmp_path: Path) -> None:
    """Verify test get file lines rejects range beyond file."""
    f = tmp_path / "sample.txt"
    f.write_text("line one\nline two\n", encoding="utf-8")

    with patch.object(BaseMCPCommand, "_resolve_project_root", return_value=tmp_path):
        result = await GetFileLinesCommand().execute(
            project_id=_PID,
            file_path="sample.txt",
            start_line=1,
            end_line=10,
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "INVALID_RANGE"
    assert "out of file bounds" in result.message.lower()


@pytest.mark.asyncio
async def test_get_file_lines_accepts_in_range_slice(tmp_path: Path) -> None:
    """Verify test get file lines accepts in range slice."""
    f = tmp_path / "sample.txt"
    f.write_text("line one\nline two\nline three\n", encoding="utf-8")

    with patch.object(BaseMCPCommand, "_resolve_project_root", return_value=tmp_path):
        result = await GetFileLinesCommand().execute(
            project_id=_PID,
            file_path="sample.txt",
            start_line=2,
            end_line=3,
        )

    assert isinstance(result, SuccessResult)
    assert result.data["lines"] == ["line two", "line three"]
    assert result.data["start_line"] == 2
    assert result.data["end_line"] == 3
