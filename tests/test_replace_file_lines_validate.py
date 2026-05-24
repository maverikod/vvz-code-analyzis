"""Tests for replace_file_lines range validation (reject OOB, no clamp)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.replace_file_lines_command import ReplaceFileLinesCommand

_PID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.asyncio
async def test_replace_file_lines_rejects_range_beyond_file(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("alpha\nbeta\n", encoding="utf-8")

    with (
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=tmp_path),
        patch(
            "code_analysis.commands.replace_file_lines_command.commit_after_write",
            return_value=(True, None),
        ),
    ):
        result = await ReplaceFileLinesCommand().execute(
            project_id=_PID,
            file_path="notes.txt",
            start_line=1,
            end_line=5,
            new_lines=["x"],
            backup=False,
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "INVALID_RANGE"
    assert f.read_text(encoding="utf-8") == "alpha\nbeta\n"


@pytest.mark.asyncio
async def test_replace_file_lines_accepts_in_range_replace(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    with (
        patch.object(BaseMCPCommand, "_resolve_project_root", return_value=tmp_path),
        patch(
            "code_analysis.commands.replace_file_lines_command.commit_after_write",
            return_value=(True, None),
        ),
    ):
        result = await ReplaceFileLinesCommand().execute(
            project_id=_PID,
            file_path="notes.txt",
            start_line=2,
            end_line=2,
            new_lines=["BETA"],
            backup=False,
        )

    assert isinstance(result, SuccessResult)
    assert f.read_text(encoding="utf-8") == "alpha\nBETA\ngamma"
