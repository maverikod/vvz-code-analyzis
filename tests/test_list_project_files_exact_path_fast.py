"""
Tests for the ``list_project_files`` exact-path fast path (bug 04cb1578).

A literal (non-glob) ``file_pattern``/``glob`` that names one on-disk, indexed,
non-ignored regular file must skip the full-project walk (``enumerate_project_paths``)
and the page-scoped ``files`` row lookup (``get_file_rows_by_paths``, bug
25c8d9dd), returning the same page-payload shape a full walk would. Also
covers the walk path's own subtree-scoping (bug 25c8d9dd) and its page-scoped
DB enrichment, which replaced the old full-table ``get_project_file_rows`` load.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
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
    calls = {"get_file_rows_by_paths": 0, "get_file_by_path": 0}

    def _get_file_rows_by_paths(
        driver: Any,
        project_id: str,
        relative_paths: list,
        include_deleted: bool = False,
    ) -> list:
        """Route the slow-path page-scoped row lookup.

        Mirrors production filtering: only rows whose ``relative_path`` is
        among the requested ``relative_paths`` are returned -- lets tests
        assert exactly which paths were requested without the mock silently
        handing back unrelated fixture rows.
        """
        calls["get_file_rows_by_paths"] += 1
        wanted = set(relative_paths)
        return [dict(row) for rel, row in rows_by_rel.items() if rel in wanted]

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

    monkeypatch.setattr(
        list_files_mod, "get_file_rows_by_paths", _get_file_rows_by_paths
    )
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


def _capture_os_walk_starts(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    """Capture every directory ``os.walk`` was invoked with (subtree-scope check).

    Patches ``os.walk`` in ``code_analysis.core.venv_path_policy`` (where the
    real walk lives) with a pass-through wrapper that records each ``top``
    argument before delegating to the real ``os.walk`` -- proves whether the
    walk started at the pattern's static-prefix subtree or fell back to the
    whole project root (bug 25c8d9dd).
    """
    import code_analysis.core.venv_path_policy as venv_path_policy_mod

    starts: List[str] = []
    real_walk = venv_path_policy_mod.os.walk

    def _walk(top: Any, *args: Any, **kwargs: Any) -> Any:
        """Record ``top`` then delegate to the real ``os.walk``."""
        starts.append(str(top))
        return real_walk(top, *args, **kwargs)

    monkeypatch.setattr(venv_path_policy_mod.os, "walk", _walk)
    return starts


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
    assert mock_db.calls["get_file_rows_by_paths"] == 0
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
    """A pattern with fnmatch metacharacters must always use the (now subtree-bounded) walk."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("x=1\n")

    pid = "00000000-0000-0000-0000-0000000000f2"
    _install_mock_db(monkeypatch)
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)
    walk_starts = _capture_os_walk_starts(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid, file_pattern="src/*.py")

    assert enum_counter["n"] == 1
    assert result.data is not None
    assert result.data["total"] == 1
    # bug 25c8d9dd: the walk still happens once (fnmatch magic means no
    # exact-file fast path), but must be bounded to "src" -- the pattern's
    # static prefix -- not the whole project root.
    assert walk_starts == [str((root / "src").resolve())]


@pytest.mark.asyncio
async def test_directory_prefix_pattern_falls_back(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A literal pattern naming a directory (not a file) must fall back to a (now
    subtree-bounded) walk."""
    root = tmp_path / "proj"
    root.mkdir()
    plan = root / "docs" / "plans" / "myplan"
    plan.mkdir(parents=True)
    (plan / "README.md").write_text("#\n")

    pid = "00000000-0000-0000-0000-0000000000f3"
    _install_mock_db(monkeypatch)
    enum_counter = _wrap_enumerate_with_counter(monkeypatch)
    walk_starts = _capture_os_walk_starts(monkeypatch)

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
    # bug 25c8d9dd: a literal directory-prefix pattern is its own static
    # prefix and names an existing directory, so the walk must start there,
    # not at the project root.
    assert walk_starts == [str(plan.resolve())]


@pytest.mark.asyncio
async def test_unscoped_pattern_walk_starts_at_project_root(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pattern with no derivable static prefix must walk from the project root."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.py").write_text("#\n")
    (root / "sub").mkdir()
    (root / "sub" / "b.py").write_text("#\n")

    pid = "00000000-0000-0000-0000-0000000000fc"
    _install_mock_db(monkeypatch)
    walk_starts = _capture_os_walk_starts(monkeypatch)

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(project_id=pid, file_pattern="*.py")

    assert result.data is not None
    assert result.data["total"] == 2
    assert walk_starts == [str(root.resolve())]


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


@pytest.mark.asyncio
async def test_slow_path_db_lookup_is_page_scoped_not_full_table(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The slow (walk) path must enrich only the current page, not the whole project (bug 25c8d9dd).

    ``get_project_file_rows`` (the full non-deleted ``files``-table load) must
    never be called by ``list_project_files`` any more; ``get_file_rows_by_paths``
    must be called exactly once, with exactly the current page's relative paths
    -- not every on-disk path the walk discovered.
    """
    root = tmp_path / "proj"
    root.mkdir()
    for name in ("a.py", "b.py", "c.py"):
        (root / name).write_text("#\n")

    pid = "00000000-0000-0000-0000-0000000000fd"

    domain_file_rows_calls = {"n": 0}

    def _domain_get_project_file_rows(
        driver: Any, project_id: str, include_deleted: bool = False
    ) -> list:
        """Fail loud if the full-table load is ever reached from any call site."""
        domain_file_rows_calls["n"] += 1
        return []

    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.domain.files.get_project_file_rows",
        _domain_get_project_file_rows,
    )

    by_paths_calls: List[list] = []
    rows_by_rel = {
        "a.py": {"id": FID, "relative_path": "a.py", "path": "a.py"},
        "b.py": {"id": "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb", "relative_path": "b.py", "path": "b.py"},
        "c.py": {"id": "cccccccc-cccc-4ccc-cccc-cccccccccccc", "relative_path": "c.py", "path": "c.py"},
    }

    def _get_file_rows_by_paths(
        driver: Any,
        project_id: str,
        relative_paths: list,
        include_deleted: bool = False,
    ) -> list:
        """Record exactly which paths were requested; serve only those rows."""
        by_paths_calls.append(list(relative_paths))
        wanted = set(relative_paths)
        return [dict(row) for rel, row in rows_by_rel.items() if rel in wanted]

    mock_db = MagicMock()

    def _open(_self: object, auto_analyze: bool = False) -> MagicMock:
        """Return the mock DB handle."""
        return mock_db

    monkeypatch.setattr(ListProjectFilesMCPCommand, "_open_database_from_config", _open)
    monkeypatch.setattr(
        list_files_mod, "get_file_rows_by_paths", _get_file_rows_by_paths
    )

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        # page_size=2 over 3 files -> the page must exclude "c.py".
        result = await cmd.execute(project_id=pid, page_size=2, block_position=1)

    assert domain_file_rows_calls["n"] == 0
    assert len(by_paths_calls) == 1
    assert sorted(by_paths_calls[0]) == ["a.py", "b.py"]
    assert result.data is not None
    assert result.data["total"] == 3
    rels = {f["relative_path"]: f["file_id"] for f in result.data["files"]}
    assert rels == {"a.py": FID, "b.py": "bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb"}
