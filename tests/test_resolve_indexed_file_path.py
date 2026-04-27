"""Tests for resolve_indexed_file_path (DB-driven path + filesystem check)."""

from __future__ import annotations

from pathlib import Path

from code_analysis.core.resolve_indexed_file_path import resolve_indexed_file_path


def test_resolve_prefers_watch_dir_plus_project_name_plus_relative(tmp_path: Path) -> None:
    """Layout: watch_absolute_path / project_name / relative_path (matches watcher MCP resolver)."""
    watch = tmp_path / "observed"
    proj_root = watch / "code_analysis"
    proj_root.mkdir(parents=True)
    py = proj_root / "pkg" / "m.py"
    py.parent.mkdir(parents=True)
    py.write_text("x = 1\n", encoding="utf-8")

    row = {
        "id": 42,
        "path": str(tmp_path / "stale_abs_that_does_not_exist.py"),
        "relative_path": "pkg/m.py",
        "watch_absolute_path": str(watch),
        "project_name": "code_analysis",
        "project_root_path": str(proj_root),
    }
    assert resolve_indexed_file_path(row) == py.resolve()


def test_resolve_falls_back_to_root_plus_relative(tmp_path: Path) -> None:
    """When watch layout columns are missing, root_path + relative_path is used."""
    root = tmp_path / "projroot"
    root.mkdir()
    py = root / "b.py"
    py.write_text("y = 2\n", encoding="utf-8")

    row = {
        "id": 1,
        "path": str(tmp_path / "missing.py"),
        "relative_path": "b.py",
        "watch_absolute_path": None,
        "project_name": None,
        "project_root_path": str(root),
    }
    assert resolve_indexed_file_path(row) == py.resolve()


def test_resolve_returns_none_when_nothing_exists(tmp_path: Path) -> None:
    row = {
        "id": 1,
        "path": str(tmp_path / "nope.py"),
        "relative_path": "nope.py",
        "watch_absolute_path": str(tmp_path),
        "project_name": "x",
        "project_root_path": str(tmp_path / "y"),
    }
    assert resolve_indexed_file_path(row) is None
