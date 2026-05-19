from __future__ import annotations

from unittest.mock import patch

import pytest

from code_analysis.commands.fs_grep_command import FsGrepCommand


@pytest.mark.asyncio
async def test_fs_grep_skips_large_files_before_reading(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "small.txt").write_text("needle here\n", encoding="utf-8")
    (project_root / "large.txt").write_text("needle\n" * 20, encoding="utf-8")

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000001",
            pattern="needle",
            max_file_bytes=20,
        )

    assert result.data is not None
    assert result.data["match_count"] == 1
    assert result.data["matches"][0]["relative_path"] == "small.txt"
    assert result.data["files_scanned"] == 1
    assert result.data["files_skipped_large"] == 1
    assert result.data["skipped_large_samples"] == [
        {"relative_path": "large.txt", "size_bytes": 140}
    ]


@pytest.mark.asyncio
async def test_fs_grep_streams_matching_lines(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.txt").write_text("alpha\nbeta\nALPHA\n", encoding="utf-8")

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000002",
            pattern="alpha",
            case_sensitive=False,
        )

    assert result.data is not None
    assert result.data["match_count"] == 2
    assert [match["line_number"] for match in result.data["matches"]] == [1, 3]
    for match in result.data["matches"]:
        assert match["block_id"] is None
        assert match["block_type"] is None


@pytest.mark.asyncio
async def test_fs_grep_truncates_line_preview_len(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "a.txt").write_text("needle-" + ("x" * 50) + "\n", encoding="utf-8")

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000003",
            pattern="needle",
            line_preview_len=10,
        )

    assert result.data is not None
    assert result.data["matches"][0]["line"] == "needle-xxx"


@pytest.mark.asyncio
async def test_fs_grep_python_match_includes_block_id(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    py_path = project_root / "sample.py"
    py_path.write_text(
        "def hello():\n    return 'needle'\n",
        encoding="utf-8",
    )
    from code_analysis.core.cst_tree.tree_builder import load_file_to_tree, remove_tree

    tree = load_file_to_tree(str(py_path))
    remove_tree(tree.tree_id)

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000004",
            pattern="needle",
            python_only=True,
        )

    assert result.data is not None
    match = result.data["matches"][0]
    assert match["relative_path"] == "sample.py"
    assert match["block_id"] is not None
    assert match["block_type"] is not None
