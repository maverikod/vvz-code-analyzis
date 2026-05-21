from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.fs_grep_budget import (
    GREP_BUDGET_EXCEEDED,
    GREP_HARD_TIMEOUT,
)
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
            fast_text_only=True,
            enrich_blocks=False,
        )

    assert result.data is not None
    assert result.data["match_count"] == 2
    assert [match["line_number"] for match in result.data["matches"]] == [1, 3]
    for match in result.data["matches"]:
        assert match.get("block_id") is None
        assert match.get("block_type") is None
        assert match.get("enrichment_status") == "skipped_fast_text_only"


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
            fast_text_only=False,
            enrich_blocks=True,
        )

    assert result.data is not None
    match = result.data["matches"][0]
    assert match["relative_path"] == "sample.py"
    assert match["block_id"] is not None
    assert match["block_type"] is not None


def test_fs_grep_auto_queue_on_inline_timeout_default() -> None:
    schema = FsGrepCommand.get_schema()
    props = schema["properties"]
    assert FsGrepCommand.use_queue is False
    assert props["auto_queue_on_inline_timeout"]["default"] is True
    assert props["inline_timeout_seconds"]["default"] == 3.0


@pytest.mark.asyncio
async def test_fs_grep_stops_at_max_matches_before_scanning_all_files(
    tmp_path,
) -> None:
    project_root = tmp_path / "project"
    pkg = project_root / "code_analysis"
    pkg.mkdir(parents=True)
    for i in range(200):
        (pkg / f"mod_{i}.py").write_text("xpath\n", encoding="utf-8")

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000005",
            pattern="xpath",
            literal=True,
            case_sensitive=False,
            file_pattern="code_analysis",
            max_matches=50,
        )

    assert result.data is not None
    assert result.data["match_count"] == 50
    assert result.data["truncated"] is True
    assert result.data["files_scanned"] < 200
    assert result.data["execution_mode"] in ("sync", "queued_recommended")
    assert "grep_budget" in result.data


@pytest.mark.asyncio
async def test_fs_grep_xpath_production_params_return_success_not_timeout(
    tmp_path,
) -> None:
    """Regression: broad xpath grep must finish sync without hanging."""
    project_root = tmp_path / "project"
    pkg = project_root / "code_analysis"
    pkg.mkdir(parents=True)
    (pkg / "one.py").write_text("xpath selector\n", encoding="utf-8")
    for i in range(30):
        (pkg / f"extra_{i}.py").write_text("no hit here\n", encoding="utf-8")

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="8772a086-688d-4198-a0c4-f03817cc0e6c",
            pattern="xpath",
            literal=True,
            case_sensitive=False,
            file_pattern="code_analysis",
            max_matches=50,
            fast_text_only=True,
            enrich_blocks=False,
            show_hidden=False,
            show_venv=False,
        )

    assert result.data is not None
    assert result.data["success"] is True
    assert result.data["fast_text_only"] is True
    assert result.data["match_count"] >= 1
    for match in result.data["matches"]:
        assert match.get("block_id") is None


@pytest.mark.asyncio
async def test_fs_grep_budget_exceeded_warning_when_file_cap_hit(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    for i in range(400):
        (project_root / f"f_{i}.txt").write_text("needle\n", encoding="utf-8")

    with patch.object(
        FsGrepCommand, "_resolve_project_root", return_value=project_root
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000006",
            pattern="needle",
            max_matches=500,
            max_files_scanned=10,
            wall_time_budget_s=30.0,
        )

    assert result.data is not None
    assert result.data["budget_exceeded"] is True
    codes = [w.get("code") for w in result.data.get("warnings") or []]
    assert GREP_BUDGET_EXCEEDED in codes


@pytest.mark.asyncio
async def test_fs_grep_hard_timeout_returns_controlled_error(tmp_path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "slow.txt").write_text("needle\n", encoding="utf-8")

    def _slow_sync(*_args: object, **_kwargs: object) -> SuccessResult:
        time.sleep(3)
        return SuccessResult(data={"matches": [], "match_count": 0, "files_scanned": 0})

    with (
        patch.object(FsGrepCommand, "_resolve_project_root", return_value=project_root),
        patch.object(FsGrepCommand, "_execute_sync", side_effect=_slow_sync),
    ):
        cmd = FsGrepCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-000000000099",
            pattern="needle",
            hard_timeout_seconds=1,
        )

    assert result.code == GREP_HARD_TIMEOUT
    assert "hard timeout" in (result.message or "").lower()
    assert (result.details or {}).get("hard_timeout_seconds") == 1
