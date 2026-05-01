"""
Tests for read_project_text_file and write_project_text_lines.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.project_text_file_guard import (
    FORBIDDEN_NON_PYTHON_CODE_SUFFIXES,
    FORBIDDEN_PYTHON_SOURCE_SUFFIXES,
    FORBIDDEN_TEXT_SUFFIXES,
    is_python_text_path,
    reject_if_python_text_path,
    reject_if_non_python_code_text_path,
    reject_if_source_code_text_path,
)
from code_analysis.commands.read_project_text_file_command import (
    ReadProjectTextFileCommand,
)
from code_analysis.commands.write_project_text_lines_command import (
    WriteProjectTextLinesCommand,
)
from code_analysis.commands.line_command_cst_gate import healthy_parse_blocks_line_ops

_PID = "550e8400-e29b-41d4-a716-446655440000"


class TestHealthyParseBlocksLineOps:
    def test_internal_allow_skips_cst_gate(self) -> None:
        assert not healthy_parse_blocks_line_ops(
            "x = 1\n",
            allow_healthy_line_ops=True,
            allow_line_commands_on_healthy_files=False,
        )

    def test_unhealthy_parse_allows_line_ops(self) -> None:
        assert not healthy_parse_blocks_line_ops(
            "def oops(\n",
            allow_healthy_line_ops=False,
            allow_line_commands_on_healthy_files=False,
        )

    def test_healthy_parse_blocks_without_allow(self) -> None:
        assert healthy_parse_blocks_line_ops(
            "def f():\n    pass\n",
            allow_healthy_line_ops=False,
            allow_line_commands_on_healthy_files=False,
        )


class TestIsPythonTextPath:
    def test_python_suffixes(self) -> None:
        assert is_python_text_path("pkg/foo.py")
        assert is_python_text_path("X.PYI")

    def test_non_python(self) -> None:
        assert not is_python_text_path("README.md")
        assert not is_python_text_path("main.go")


class TestRejectIfPythonTextPath:
    def test_allows_md_and_unknown(self) -> None:
        assert reject_if_python_text_path("README.md") is None
        assert reject_if_python_text_path("dir/config.toml") is None

    @pytest.mark.parametrize(
        "path", ["x.py", "pkg/X.PYI", "w.PyW", "a/b/c.py", "mod.pyx"]
    )
    def test_rejects_python_suffixes(self, path: str) -> None:
        r = reject_if_python_text_path(path)
        assert isinstance(r, ErrorResult)
        assert r.code == "PYTHON_FILE_FORBIDDEN"
        assert Path(path).suffix.lower() in FORBIDDEN_PYTHON_SOURCE_SUFFIXES


class TestRejectIfNonPythonCodeTextPath:
    @pytest.mark.parametrize("path", ["main.go", "lib.rs", "x.java", "n.ipynb"])
    def test_rejects_code_suffixes(self, path: str) -> None:
        r = reject_if_non_python_code_text_path(path)
        assert isinstance(r, ErrorResult)
        assert r.code == "CODE_FILE_FORBIDDEN"
        assert Path(path).suffix.lower() in FORBIDDEN_NON_PYTHON_CODE_SUFFIXES

    def test_allows_python_paths_for_this_layer(self) -> None:
        assert reject_if_non_python_code_text_path("a.py") is None


class TestRejectIfSourceCodeTextPath:
    def test_python_takes_precedence_message(self) -> None:
        r = reject_if_source_code_text_path("pkg/foo.py")
        assert isinstance(r, ErrorResult)
        assert r.code == "PYTHON_FILE_FORBIDDEN"
        assert "CST" in (r.message or "")

    def test_non_python_code(self) -> None:
        r = reject_if_source_code_text_path("src/main.go")
        assert isinstance(r, ErrorResult)
        assert r.code == "CODE_FILE_FORBIDDEN"

    def test_allowed_plain_text(self) -> None:
        assert reject_if_source_code_text_path("README.md") is None
        assert reject_if_source_code_text_path("cfg/app.toml") is None

    def test_union_matches_documented_suffix_lists(self) -> None:
        assert FORBIDDEN_TEXT_SUFFIXES == (
            FORBIDDEN_PYTHON_SOURCE_SUFFIXES | FORBIDDEN_NON_PYTHON_CODE_SUFFIXES
        )


@pytest.mark.asyncio
class TestReadProjectTextFile:
    async def test_reads_range(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("a\nb\nc\nd\n", encoding="utf-8")
        mock_db = MagicMock()
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
        ):
            cmd = ReadProjectTextFileCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes.txt",
                start_line=2,
                end_line=3,
            )
        assert isinstance(result, SuccessResult)
        assert result.data["lines"] == ["b", "c"]
        assert result.data["total_lines"] == 4
        assert result.data["start_line"] == 2
        assert result.data["end_line"] == 3
        assert result.data.get("handler_id") == "text"

    async def test_text_invalid_range_after_resolve(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("a\n", encoding="utf-8")
        mock_db = MagicMock()
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
        ):
            cmd = ReadProjectTextFileCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes.txt",
                start_line=5,
                end_line=1,
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_RANGE"

    async def test_routes_healthy_python_to_get_file_lines(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "foo.py"
        f.write_text("def foo():\n    return 42\n", encoding="utf-8")
        mock_db = MagicMock()
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
        ):
            cmd = ReadProjectTextFileCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="foo.py",
                start_line=1,
                end_line=2,
            )
        assert isinstance(result, SuccessResult)
        assert result.data["lines"] == ["def foo():", "    return 42"]
        assert result.data.get("success") is True
        assert result.data.get("handler_id") == "python"

    async def test_python_invalid_range_delegates_to_get_file_lines(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "bad.py"
        f.write_text("a\n", encoding="utf-8")
        mock_db = MagicMock()
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
        ):
            cmd = ReadProjectTextFileCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="bad.py",
                start_line=10,
                end_line=1,
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_RANGE"

    async def test_rejects_go_before_resolve(self) -> None:
        cmd = ReadProjectTextFileCommand()
        result = await cmd.execute(
            project_id=_PID,
            file_path="main.go",
            start_line=1,
            end_line=1,
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "CODE_FILE_FORBIDDEN"

    async def test_json_small_returns_structured_like_json_load(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "data.json"
        f.write_text('{"hello": "world"}\n', encoding="utf-8")
        mock_db = MagicMock()
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
        ):
            cmd = ReadProjectTextFileCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="data.json",
                start_line=99,
                end_line=1,
            )
        assert isinstance(result, SuccessResult)
        d = result.data
        assert "lines" not in d
        assert d.get("success") is True
        assert d.get("handler_id") == "json"
        assert d.get("tree_id")
        assert d.get("root_node_id")
        assert isinstance(d.get("nodes"), list)
        assert d.get("total_nodes", 0) >= 1

    async def test_json_large_file_still_structured_via_handler(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "big.json"
        payload = '{"pad":"' + ("x" * 80) + '"}'
        f.write_text(payload, encoding="utf-8")
        assert f.stat().st_size > 64
        mock_db = MagicMock()
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
        ):
            cmd = ReadProjectTextFileCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="big.json",
                start_line=1,
                end_line=10,
            )
        assert isinstance(result, SuccessResult)
        assert "lines" not in result.data
        assert result.data.get("handler_id") == "json"
        assert result.data.get("tree_id")
        assert isinstance(result.data.get("nodes"), list)

    async def test_json_invalid_returns_handler_validation_failed(
        self, tmp_path: Path
    ) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{ not json", encoding="utf-8")
        mock_db = MagicMock()
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
        ):
            cmd = ReadProjectTextFileCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="bad.json",
                start_line=1,
                end_line=5,
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "validation_failed"


@pytest.mark.asyncio
class TestWriteProjectTextLines:
    async def test_replaces_range(self, tmp_path: Path) -> None:
        cfg = tmp_path / "notes.txt"
        cfg.write_text("a\nb\nc\n", encoding="utf-8")
        mock_db = MagicMock()
        mock_proj = MagicMock()
        mock_proj.root_path = str(tmp_path)
        mock_db.get_project.return_value = mock_proj
        mock_db.select.return_value = [{"id": 99}]

        meta_calls: list[dict[str, object]] = []

        def _capture_meta(**kwargs: object) -> dict[str, object]:
            meta_calls.append(dict(kwargs))
            return {"success": True, "file_id": 99, "metadata_only": True}

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=cfg,
            ),
            patch(
                "code_analysis.commands.write_project_text_lines_command.persist_plain_text_file_metadata",
                side_effect=_capture_meta,
            ),
            patch(
                "code_analysis.commands.write_project_text_lines_command.BackupManager"
            ) as bm_cls,
        ):
            bm_cls.return_value.create_backup.return_value = "bu-1"
            cmd = WriteProjectTextLinesCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes.txt",
                start_line=2,
                end_line=2,
                new_lines=["X"],
                backup=True,
            )

        assert isinstance(result, SuccessResult)
        # join() does not add a trailing newline after the last line (same as replace_file_lines)
        assert cfg.read_text(encoding="utf-8") == "a\nX\nc"
        assert len(meta_calls) == 1
        assert meta_calls[0].get("project_id") == _PID
        mock_db.update_file.assert_not_called()
        mock_db.begin_transaction.assert_not_called()
        mock_db.commit_transaction.assert_not_called()
        mock_db.rollback_transaction.assert_not_called()

    async def test_metadata_failure_restores_file_when_backup(
        self, tmp_path: Path
    ) -> None:
        cfg = tmp_path / "notes.txt"
        original = "line1\nline2\n"
        cfg.write_text(original, encoding="utf-8")
        mock_db = MagicMock()
        mock_proj = MagicMock()
        mock_proj.root_path = str(tmp_path)
        mock_db.get_project.return_value = mock_proj
        mock_db.select.return_value = [{"id": 42}]

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=cfg,
            ),
            patch(
                "code_analysis.commands.write_project_text_lines_command.persist_plain_text_file_metadata",
                return_value={"success": False, "error": "db failed"},
            ),
            patch(
                "code_analysis.commands.write_project_text_lines_command.BackupManager"
            ) as bm_cls,
        ):
            bm_cls.return_value.create_backup.return_value = "bu-restore"
            bm_inst = bm_cls.return_value
            cmd = WriteProjectTextLinesCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path="notes.txt",
                start_line=1,
                end_line=1,
                new_lines=["new"],
                backup=True,
            )

        assert isinstance(result, ErrorResult)
        assert result.code == "UPDATE_FILE_DATA_ERROR"
        bm_inst.restore_file.assert_called_once_with(
            "notes.txt",
            "bu-restore",
        )

    async def test_rejects_python_paths_before_resolve(self) -> None:
        cmd = WriteProjectTextLinesCommand()
        for path in ("pkg/mod.py", "types.pyi"):
            result = await cmd.execute(
                project_id=_PID,
                file_path=path,
                start_line=1,
                end_line=1,
                new_lines=["x"],
            )
            assert isinstance(result, ErrorResult)
            assert result.code == "PYTHON_FILE_FORBIDDEN"

    async def test_rejects_code_before_invalid_range(self) -> None:
        cmd = WriteProjectTextLinesCommand()
        result = await cmd.execute(
            project_id=_PID,
            file_path="app.rs",
            start_line=5,
            end_line=1,
            new_lines=["x"],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "CODE_FILE_FORBIDDEN"

    async def test_rejects_go_suffix(self) -> None:
        cmd = WriteProjectTextLinesCommand()
        result = await cmd.execute(
            project_id=_PID,
            file_path="main.go",
            start_line=1,
            end_line=1,
            new_lines=["x"],
        )
        assert isinstance(result, ErrorResult)
        assert result.code == "CODE_FILE_FORBIDDEN"

    async def test_rejects_json_not_plain_text_allowlist(self) -> None:
        cmd = WriteProjectTextLinesCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="data.json",
                start_line=1,
                end_line=1,
                new_lines=["x"],
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "TEXT_FILE_SUFFIX_NOT_ALLOWED"
        odb.assert_not_called()

    async def test_invalid_range_before_database_open(self) -> None:
        cmd = WriteProjectTextLinesCommand()
        with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
            result = await cmd.execute(
                project_id=_PID,
                file_path="README.md",
                start_line=4,
                end_line=1,
                new_lines=["x"],
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "INVALID_RANGE"
        odb.assert_not_called()

    async def test_rejects_write_under_project_venv(self, tmp_path: Path) -> None:
        vdir = tmp_path / ".venv"
        vdir.mkdir(parents=True, exist_ok=True)
        cfg = vdir / "notes.txt"
        cfg.write_text("a\nb\n", encoding="utf-8")
        mock_db = MagicMock()
        mock_proj = MagicMock()
        mock_proj.root_path = str(tmp_path)
        mock_db.get_project.return_value = mock_proj

        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch.object(
                BaseMCPCommand,
                "_resolve_file_path_from_project",
                return_value=cfg,
            ),
            patch(
                "code_analysis.commands.write_project_text_lines_command.BackupManager"
            ),
        ):
            cmd = WriteProjectTextLinesCommand()
            result = await cmd.execute(
                project_id=_PID,
                file_path=".venv/notes.txt",
                start_line=1,
                end_line=1,
                new_lines=["x"],
            )

        assert isinstance(result, ErrorResult)
        assert result.code == "PROJECT_VENV_WRITE_FORBIDDEN"
