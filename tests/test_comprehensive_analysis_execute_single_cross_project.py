"""
Cross-project safety for comprehensive_analysis single-file execution.

Ensures execute_single does not clear, mark deleted, or add_file when the same
absolute path exists only under another project's DB row.
"""

from __future__ import annotations

import logging
import time
from unittest.mock import MagicMock

import pytest

from code_analysis.commands.comprehensive_analysis_mcp.execute_single import (
    run_single_file,
)


@pytest.fixture(autouse=True)
def _patch_get_file_by_path_to_db_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route the domain ``get_file_by_path`` call site back to ``db.get_file_by_path``.

    ``run_single_file`` calls the driver-direct free function (stage-2 layer
    collapse), which reads through ``driver.select``/``driver.execute`` -
    primitives the bare ``MagicMock()`` db in this module does not model.
    Every test here sets ``db.get_file_by_path = MagicMock(...)`` and asserts
    on its call_args_list directly, so redirect the call site to that mock
    instead of exercising real SQL composition.
    """
    monkeypatch.setattr(
        "code_analysis.commands.comprehensive_analysis_mcp.execute_single.get_file_by_path",
        lambda driver, path, project_id, include_deleted=False: driver.get_file_by_path(
            path, project_id, include_deleted=include_deleted
        ),
    )
    # Same reasoning for save_comprehensive_analysis_results: tests assert on
    # db.save_comprehensive_analysis_results.assert_called_once(), so route the
    # domain free-function call site back to that mock too.
    monkeypatch.setattr(
        "code_analysis.commands.comprehensive_analysis_mcp.execute_single."
        "save_comprehensive_analysis_results",
        lambda driver, **kwargs: driver.save_comprehensive_analysis_results(**kwargs),
    )


def _empty_results() -> dict:
    """Return empty results."""
    return {
        "placeholders": [],
        "stubs": [],
        "empty_methods": [],
        "imports_not_at_top": [],
        "long_files": [],
        "duplicates": [],
        "flake8_errors": [],
        "mypy_errors": [],
        "missing_docstrings": [],
        "summary": {},
    }


def _base_ctx(tmp_path, proj_id: str, rel_file: str) -> dict:
    """Return base ctx."""
    return {
        "db": MagicMock(),
        "root_path": tmp_path,
        "proj_id": proj_id,
        "analysis_logger": logging.getLogger("test_ca_cross_project"),
        "log_timing": lambda _phase, t0: time.perf_counter(),
        "progress_tracker": None,
        "analyzer": MagicMock(),
        "results": _empty_results(),
        "mypy_config": None,
        "file_path": rel_file,
        "check_placeholders": False,
        "check_stubs": False,
        "check_empty_methods": False,
        "check_imports": False,
        "check_duplicates": False,
        "check_flake8": False,
        "check_mypy": False,
        "check_docstrings": False,
        "duplicate_min_lines": 5,
        "duplicate_min_similarity": 0.8,
    }


@pytest.mark.asyncio
async def test_resolves_when_file_row_under_requested_project(tmp_path) -> None:
    """Verify test resolves when file row under requested project."""
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    abs_path = str((tmp_path / "mod.py").resolve())

    ctx = _base_ctx(tmp_path, "proj-a", "mod.py")
    db = ctx["db"]
    db.get_file_by_path = MagicMock(
        return_value={"id": 42, "project_id": "proj-a", "deleted": 0}
    )
    db.should_analyze_file = MagicMock(
        return_value={
            "should_analyze": True,
            "reason": "stale",
            "db_mtime": 0,
            "disk_mtime": 1,
        }
    )
    db.disconnect = MagicMock()
    db.save_comprehensive_analysis_results = MagicMock()
    db.execute = MagicMock()

    cmd = MagicMock()
    cmd._validate_file_path = lambda fp, root: (root / fp).resolve()

    await run_single_file(cmd, ctx)

    db.get_file_by_path.assert_called()
    first_kw = db.get_file_by_path.call_args_list[0]
    assert first_kw[0][0] == abs_path
    assert first_kw[0][1] == "proj-a"
    db.clear_file_data.assert_not_called()
    db.add_file.assert_not_called()
    db.save_comprehensive_analysis_results.assert_called_once()
    kwargs = db.save_comprehensive_analysis_results.call_args.kwargs
    assert kwargs["file_id"] == 42
    assert kwargs["project_id"] == "proj-a"


@pytest.mark.asyncio
async def test_same_abs_path_other_project_no_clear_no_update_no_add(tmp_path) -> None:
    """Verify test same abs path other project no clear no update no add."""
    (tmp_path / "shared.py").write_text("y = 2\n", encoding="utf-8")
    abs_path = str((tmp_path / "shared.py").resolve())

    ctx = _base_ctx(tmp_path, "proj-a", "shared.py")
    db = ctx["db"]
    db.get_file_by_path = MagicMock(return_value=None)
    db.disconnect = MagicMock()
    db.save_comprehensive_analysis_results = MagicMock()
    db.clear_file_data = MagicMock()
    db.add_file = MagicMock()
    db.execute = MagicMock(
        return_value={
            "data": [
                {
                    "id": 999,
                    "project_id": "proj-b",
                    "deleted": 0,
                }
            ]
        }
    )

    cmd = MagicMock()
    cmd._validate_file_path = lambda fp, root: (root / fp).resolve()

    await run_single_file(cmd, ctx)

    assert len(db.get_file_by_path.call_args_list) == 2
    c0 = db.get_file_by_path.call_args_list[0]
    assert c0.args[0] == abs_path and c0.args[1] == "proj-a"
    assert c0.kwargs.get("include_deleted") is False
    c1 = db.get_file_by_path.call_args_list[1]
    assert c1.args[0] == abs_path and c1.args[1] == "proj-a"
    assert c1.kwargs.get("include_deleted") is True
    db.execute.assert_called_once_with(
        "SELECT id, project_id, deleted FROM files WHERE path = ? LIMIT 1",
        (abs_path,),
    )
    db.clear_file_data.assert_not_called()
    db.add_file.assert_not_called()
    # No second execute for UPDATE deleted
    assert db.execute.call_count == 1
    db.save_comprehensive_analysis_results.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_uses_absolute_path_not_relative_only(tmp_path) -> None:
    """Another project may share relative_path under a different root; only abs path matters."""
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "t.py").write_text("pass\n", encoding="utf-8")
    abs_path = str((sub / "t.py").resolve())

    ctx = _base_ctx(tmp_path, "p-indexed", "pkg/t.py")
    db = ctx["db"]
    db.get_file_by_path = MagicMock(return_value=None)
    db.disconnect = MagicMock()
    db.save_comprehensive_analysis_results = MagicMock()
    db.execute = MagicMock(return_value={"data": []})

    cmd = MagicMock()
    cmd._validate_file_path = lambda fp, root: (root / fp).resolve()

    await run_single_file(cmd, ctx)

    for call in db.get_file_by_path.call_args_list:
        assert call[0][0] == abs_path
        assert call[0][1] == "p-indexed"
    db.execute.assert_called_once_with(
        "SELECT id, project_id, deleted FROM files WHERE path = ? LIMIT 1",
        (abs_path,),
    )
    db.clear_file_data.assert_not_called()


@pytest.mark.asyncio
async def test_unindexed_on_disk_other_project_owns_abs_no_steal(tmp_path) -> None:
    """No row for requested project; disk file exists; other project has same abs — no mutations."""
    (tmp_path / "only_here.py").write_text("# ok\n", encoding="utf-8")
    abs_path = str((tmp_path / "only_here.py").resolve())

    ctx = _base_ctx(tmp_path, "want-me", "only_here.py")
    db = ctx["db"]
    db.get_file_by_path = MagicMock(return_value=None)
    db.disconnect = MagicMock()
    db.clear_file_data = MagicMock()
    db.add_file = MagicMock()
    db.execute = MagicMock(
        return_value={
            "data": [{"id": 1, "project_id": "owner-other", "deleted": 0}],
        }
    )

    cmd = MagicMock()
    cmd._validate_file_path = lambda fp, root: (root / fp).resolve()

    await run_single_file(cmd, ctx)

    db.clear_file_data.assert_not_called()
    db.add_file.assert_not_called()
