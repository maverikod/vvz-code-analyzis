"""
Tests for the ``list_project_files`` exact-path fast path (bug 04cb1578).

A literal (non-glob) ``file_pattern``/``glob`` that names one on-disk, indexed,
non-ignored regular file must skip the full-project walk (``enumerate_project_paths``)
and the full ``files`` table load (``get_project_file_rows``), returning the same
page-payload shape a full walk would.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.ast import list_files as list_files_mod
from code_analysis.commands.ast.list_files import ListProjectFilesMCPCommand

FID = "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee"


def _install_mock_db(
    monkeypatch: pytest.MonkeyPatch,
    rows_by_rel: Optional[Dict[str, Dict[str, Any]]] = None,
) -> MagicMock:
    """Install a mock DB for both the slow-path row-table load and the fast-path lookup.

    ``rows_by_rel`` maps project-relative POSIX path -> a dict that mimics a
    ``files`` table row (``id``, ``relative_path``, ``path`` at minimum).
    """
    rows_by_rel = rows_by_rel or {}
    mock_db = MagicMock()

    def _open(_self: object, auto_analyze: bool = False) -> MagicMock:
        """Return the mock DB handle."""
        return mock_db

    monkeypatch.setattr(
        ListProjectFilesMCPCommand, "_open_database_from_config", _open
    )

    all_rows = list(rows_by_rel.values())
    calls = {"get_project_file_rows": 0, "get_file_by_path": 0}

    def _get_project_file_rows(
        driver: Any, project_id: str, include_deleted: bool = False
    ) -> list:
        """Route the slow-path row-table load."""
        calls["get_project_file_rows"] += 1
        return all_rows

    def _get_file_by_path(
        driver: Any, path: str, project_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Route the fast-path single-row lookup."""
        calls["get_file_by_path"] += 1
        norm = str(path).replace("\\", "/")
        for rel, row in rows_by_rel.items():
            if norm.endswith(rel):
                return dict(row)
        return None

    monkeypatch.setattr(list_files_mod, "get_project_file_rows", _get_project_file_rows)
    monkeypatch.setattr(list_files_mod, "get_file_by_path", _get_file_by_path)
    mock_db.calls = calls  # type: ignore[attr-defined]
    return mock_db


def _wrap_enumerate_with_counter(monkeypatch: pytest.MonkeyPatch) -> Dict[str, int]:
    """Wrap ``enumerate_project_paths`` in list_files_mod with a call counter."""
    counter = {"n": 0}
    original = list_files_mod.enumerate_project_paths

    def _counting(*args: Any, **kwargs: Any) -> Any:
        counter["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(list_files_mod, "enumerate_project_paths", _counting)
    return counter


@pytest.mark.asyncio
async def test_literal_pattern_engages_fast_path_and_matches_slow_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fast path must skip enumerate_project_paths and byte-match the slow path."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x=1\n")
    (root / "src" / "other.py").write_text("y=2\n")

    pid = "00000000-0000-0000-0000-0000000000f1"
    rel = "src/app.py"
    mock_db = _install_mock_db(
        monkeypatch, {rel: {"id": FID, "relative_path": rel, "path": rel}}
    )
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        fast_result = await cmd.execute(project_id=pid, file_pattern=rel)

    assert enum_counter["n"] == 0
    assert mock_db.calls["get_project_file_rows"] == 0
    assert mock_db.calls["get_file_by_path"] == 1
    assert fast_result.data is not None
    fast_data = fast_result.data
    assert fast_data["total"] == 1
    assert fast_data["files"][0]["relative_path"] == rel
    assert fast_data["files"][0]["file_id"] == FID

    # Force the slow path for the same query (disable fnmatch-magic detection so
    # the literal-candidate helper never engages the fast path) and compare.
    monkeypatch.setattr(list_files_mod, "pattern_has_fnmatch_magic", lambda p: True)
    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd2 = ListProjectFilesMCPCommand()
        slow_result = await cmd2.execute(project_id=pid, file_pattern=rel)

    assert enum_counter["n"] == 1
    assert slow_result.data is not None
    assert slow_result.data == fast_data


@pytest.mark.asyncio
async def test_glob_pattern_falls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pattern with fnmatch metacharacters must always use the full walk."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x=1\n")

    pid = "00000000-0000-0000-0000-0000000000f2"
    _install_mock_db(monkeypatch)
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid, file_pattern="src/*.py")

    assert enum_counter["n"] == 1
    assert result.data is not None
    assert result.data["total"] == 1


@pytest.mark.asyncio
async def test_directory_prefix_pattern_falls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A literal pattern naming a directory (not a file) must fall back."""
    root = tmp_path / "proj"
    root.mkdir()
    plan = root / "docs" / "plans" / "myplan"
    plan.mkdir(parents=True)
    (plan / "README.md").write_text("#\n")

    pid = "00000000-0000-0000-0000-0000000000f3"
    _install_mock_db(monkeypatch)
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id=pid, file_pattern="docs/plans/myplan"
        )

    assert enum_counter["n"] == 1
    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["files"][0]["relative_path"] == "docs/plans/myplan/README.md"


@pytest.mark.asyncio
async def test_missing_file_pattern_falls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A literal pattern naming a nonexistent path must fall back (and yield 0)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")

    pid = "00000000-0000-0000-0000-0000000000f4"
    _install_mock_db(monkeypatch)
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid, file_pattern="does/not/exist.py")

    assert enum_counter["n"] == 1
    assert result.data is not None
    assert result.data["total"] == 0


@pytest.mark.asyncio
async def test_indexed_file_missing_from_db_falls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An on-disk literal match with no DB row must fall back, not synthesize a hit."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "only_fs.py").write_text("#\n")

    pid = "00000000-0000-0000-0000-0000000000f5"
    _install_mock_db(monkeypatch)  # no rows at all
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid, file_pattern="only_fs.py")

    assert enum_counter["n"] == 1
    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["files"][0]["relative_path"] == "only_fs.py"
    assert result.data["files"][0]["file_id"] is None


@pytest.mark.asyncio
async def test_hidden_file_ignore_policy_matches_slow_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fast-path verdict for a dot-dir file must match the slow-path verdict."""
    root = tmp_path / "proj"
    root.mkdir()
    hidden_dir = root / ".config"
    hidden_dir.mkdir()
    (hidden_dir / "settings.py").write_text("#\n")

    pid = "00000000-0000-0000-0000-0000000000f6"
    rel = ".config/settings.py"
    _install_mock_db(monkeypatch, {rel: {"id": FID, "relative_path": rel, "path": rel}})
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        default_result = await cmd.execute(project_id=pid, file_pattern=rel)
        assert enum_counter["n"] == 1  # ignored by default -> fast path bails, falls back
        assert default_result.data is not None
        assert default_result.data["total"] == 0  # slow path agrees: hidden by default

        enum_counter["n"] = 0
        hidden_result = await cmd.execute(
            project_id=pid, file_pattern=rel, show_hidden=True
        )
        assert enum_counter["n"] == 0  # show_hidden=True -> fast path engages
        assert hidden_result.data is not None
        assert hidden_result.data["total"] == 1
        assert hidden_result.data["files"][0]["relative_path"] == rel


@pytest.mark.asyncio
async def test_venv_file_always_falls_back_regardless_of_show_venv(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``.venv``-segment literal path must always fall back to the full walk.

    Reachability there depends on RECORD parsing / ignore_exceptions expansion, not
    a simple per-path predicate, so the fast path never claims a .venv verdict --
    even when ``show_venv=True`` and the slow path (via RECORD/ignore_exceptions)
    would end up serving it.
    """
    root = tmp_path / "proj"
    root.mkdir()
    vdir = root / ".venv"
    vdir.mkdir()
    (vdir / "forced.py").write_text("x = 1\n")

    pid = "00000000-0000-0000-0000-0000000000f7"
    rel = ".venv/forced.py"
    _install_mock_db(monkeypatch, {rel: {"id": FID, "relative_path": rel, "path": rel}})
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with (
        patch.object(
            ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
        ),
        patch(
            "code_analysis.commands.project_fs_enumerate.load_ignore_exceptions_from_config",
            return_value=[".venv/forced.py"],
        ),
    ):
        cmd = ListProjectFilesMCPCommand()

        # Default (not force-included): fast path falls back; slow path agrees (0).
        off_result = await cmd.execute(project_id=pid, file_pattern=rel)
        assert enum_counter["n"] == 1
        assert off_result.data is not None
        assert off_result.data["total"] == 0

        # Force-included via include_venv_ignore_exceptions: fast path STILL falls
        # back (never claims a .venv verdict), but the slow path it defers to
        # correctly serves the file.
        enum_counter["n"] = 0
        on_result = await cmd.execute(
            project_id=pid, file_pattern=rel, include_venv_ignore_exceptions=True
        )
        assert enum_counter["n"] == 1
        assert on_result.data is not None
        assert on_result.data["total"] == 1
        assert on_result.data["files"][0]["relative_path"] == rel


@pytest.mark.asyncio
async def test_python_only_non_py_candidate_falls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``python_only=True`` with a non-``.py`` literal candidate must fall back."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "notes.md").write_text("# doc\n")

    pid = "00000000-0000-0000-0000-0000000000f8"
    _install_mock_db(
        monkeypatch,
        {"notes.md": {"id": FID, "relative_path": "notes.md", "path": "notes.md"}},
    )
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id=pid, file_pattern="notes.md", python_only=True
        )

    assert enum_counter["n"] == 1
    assert result.data is not None
    assert result.data["total"] == 0


@pytest.mark.asyncio
async def test_binary_suffix_candidate_falls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A binary-suffix literal candidate must fall back (same as the walk's skip)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "lib.so").write_bytes(b"\x00\x01")

    pid = "00000000-0000-0000-0000-0000000000f9"
    _install_mock_db(
        monkeypatch, {"lib.so": {"id": FID, "relative_path": "lib.so", "path": "lib.so"}}
    )
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid, file_pattern="lib.so")

    assert enum_counter["n"] == 1
    assert result.data is not None
    assert result.data["total"] == 0


@pytest.mark.asyncio
async def test_path_traversal_pattern_falls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``..``-escaping literal pattern must never resolve outside project_root."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")
    outside = tmp_path / "secret.py"
    outside.write_text("#\n")

    pid = "00000000-0000-0000-0000-0000000000fa"
    _install_mock_db(monkeypatch)
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid, file_pattern="../secret.py")

    assert enum_counter["n"] == 1
    assert result.data is not None
    assert result.data["total"] == 0


@pytest.mark.asyncio
async def test_glob_alias_and_pattern_precedence_still_use_fast_path(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``glob`` alias and ``file_pattern`` precedence must also engage the fast path."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")

    pid = "00000000-0000-0000-0000-0000000000fb"
    _install_mock_db(
        monkeypatch, {"a.py": {"id": FID, "relative_path": "a.py", "path": "a.py"}}
    )
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid, glob="a.py")

    assert enum_counter["n"] == 0
    assert result.data is not None
    assert result.data["total"] == 1
    assert result.data["files"][0]["file_id"] == FID
