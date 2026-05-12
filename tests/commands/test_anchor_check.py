"""
Tests for line-range anchor verification.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.anchor_check import (
    AnchorMismatch,
    check_text_anchor,
    compute_text_anchor,
)
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.replace_file_lines_command import ReplaceFileLinesCommand
from code_analysis.commands.universal_file_replace_command import (
    UniversalFileReplaceCommand,
)

_PID = "550e8400-e29b-41d4-a716-446655440000"


class TestTextAnchor:
    def test_check_text_anchor_correct_anchor_passes(self) -> None:
        lines = ["alpha beta", "gamma delta"]
        check_text_anchor(lines, 1, 2, "alpha", "delta")

    def test_check_text_anchor_wrong_head_raises(self) -> None:
        with pytest.raises(AnchorMismatch) as exc_info:
            check_text_anchor(["alpha beta"], 1, 1, "omega", "abeta")

        assert exc_info.value.details["anchor_field"] == "anchor_head"
        assert exc_info.value.details["actual"] == "alpha"

    def test_check_text_anchor_wrong_tail_raises(self) -> None:
        with pytest.raises(AnchorMismatch) as exc_info:
            check_text_anchor(["alpha beta"], 1, 1, "alpha", "omega")

        assert exc_info.value.details["anchor_field"] == "anchor_tail"
        assert exc_info.value.details["actual"] == "abeta"

    def test_check_text_anchor_none_noops(self) -> None:
        check_text_anchor(["alpha beta"], 1, 1, None, None)

    def test_check_text_anchor_blank_range_matches_empty(self) -> None:
        check_text_anchor(["   \t  "], 1, 1, "", "")

    def test_compute_text_anchor_single_line_uses_same_line_for_both_sides(
        self,
    ) -> None:
        assert compute_text_anchor(["  abc def  "], 1, 1) == {
            "anchor_head": "abcde",
            "anchor_tail": "bcdef",
        }


@pytest.mark.asyncio
class TestReplaceFileLinesAnchor:
    async def test_correct_anchor_writes(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("alpha beta\ngamma delta\n", encoding="utf-8")

        with (
            patch.object(
                BaseMCPCommand, "_resolve_project_root", return_value=tmp_path
            ),
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
                new_lines=["new value"],
                backup=False,
                anchor_head="gamma",
                anchor_tail="delta",
            )

        assert isinstance(result, SuccessResult)
        assert f.read_text(encoding="utf-8") == "alpha beta\nnew value"

    async def test_wrong_anchor_no_write_no_backup(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        original = "alpha beta\ngamma delta\n"
        f.write_text(original, encoding="utf-8")

        with (
            patch.object(
                BaseMCPCommand, "_resolve_project_root", return_value=tmp_path
            ),
            patch(
                "code_analysis.commands.replace_file_lines_command.BackupManager"
            ) as bm_cls,
        ):
            result = await ReplaceFileLinesCommand().execute(
                project_id=_PID,
                file_path="notes.txt",
                start_line=2,
                end_line=2,
                new_lines=["new value"],
                backup=True,
                anchor_head="wrong",
                anchor_tail="delta",
            )

        bm_cls.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "ANCHOR_MISMATCH"
        assert f.read_text(encoding="utf-8") == original

    async def test_anchor_node_id_with_text_anchor_validation_error(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "broken.py"
        f.write_text("def broken(\n", encoding="utf-8")

        with patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=tmp_path,
        ):
            result = await ReplaceFileLinesCommand().execute(
                project_id=_PID,
                file_path="broken.py",
                start_line=1,
                end_line=1,
                new_lines=["def fixed(): pass"],
                anchor_head="defbr",
                anchor_tail="oken(",
                anchor_node_id="stable-id",
            )

        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"

    async def test_anchor_node_id_on_non_python_validation_error(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("alpha beta\n", encoding="utf-8")

        with patch.object(
            BaseMCPCommand,
            "_resolve_project_root",
            return_value=tmp_path,
        ):
            result = await ReplaceFileLinesCommand().execute(
                project_id=_PID,
                file_path="notes.txt",
                start_line=1,
                end_line=1,
                new_lines=["new value"],
                anchor_node_id="stable-id",
            )

        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"


@pytest.mark.asyncio
class TestUniversalFileReplaceAnchor:
    async def test_single_range_wrong_anchor(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        original = "alpha beta\ngamma delta\n"
        f.write_text(original, encoding="utf-8")
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        mock_db.get_project.return_value = mock_project

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
            patch(
                "code_analysis.commands.universal_file_replace_command.BackupManager"
            ) as bm_cls,
        ):
            result = await UniversalFileReplaceCommand().execute(
                project_id=_PID,
                file_path="notes.txt",
                start_line=2,
                end_line=2,
                new_lines=["new value"],
                anchor_head="wrong",
                anchor_tail="delta",
            )

        bm_cls.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "ANCHOR_MISMATCH"
        assert f.read_text(encoding="utf-8") == original

    async def test_multi_range_wrong_second_anchor_aborts_all(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "notes.txt"
        original = "alpha beta\ngamma delta\nomega value\n"
        f.write_text(original, encoding="utf-8")
        mock_db = MagicMock()
        mock_project = MagicMock()
        mock_project.root_path = str(tmp_path)
        mock_db.get_project.return_value = mock_project

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=f,
            ),
            patch(
                "code_analysis.commands.universal_file_replace_command.BackupManager"
            ) as bm_cls,
        ):
            result = await UniversalFileReplaceCommand().execute(
                project_id=_PID,
                file_path="notes.txt",
                replacements=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "new_lines": ["first"],
                        "anchor_head": "alpha",
                        "anchor_tail": "abeta",
                    },
                    {
                        "start_line": 3,
                        "end_line": 3,
                        "new_lines": ["third"],
                        "anchor_head": "wrong",
                        "anchor_tail": "value",
                    },
                ],
            )

        bm_cls.assert_not_called()
        assert isinstance(result, ErrorResult)
        assert result.code == "ANCHOR_MISMATCH"
        assert result.details["start_line"] == 3
        assert f.read_text(encoding="utf-8") == original
