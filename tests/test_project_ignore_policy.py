"""Unit tests for :mod:`code_analysis.core.project_ignore_policy`."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.core.project_ignore_policy import (
    GIT_DIR_BASENAME,
    OLD_CODE_DIR_BASENAME,
    filter_ignore_exception_py_paths_for_watcher,
    filter_paths_for_default_project_listing,
    is_ignored_project_relative_path,
    path_is_under_project_local_venv,
    path_matches_traversal_skip_shape_rules,
    sql_and_absolute_path_eligible_for_default_status_aggregates,
)


@pytest.mark.parametrize(
    "rel,expected",
    [
        (".venv/lib/python3.12/site-packages/foo.py", True),
        (
            ".venv/lib/python3.12/site-packages/mcp_proxy_adapter/core/client.py",
            True,
        ),
        ("venv/lib/python3.12/site-packages/foo.py", True),
        (".git/config", True),
        ("node_modules/pkg/index.js", True),
        ("__pycache__/mod.cpython-312.pyc", True),
        (".pytest_cache/v/cache/lastfailed", True),
        (".mypy_cache/3.12/foo.data.json", True),
        ("dist/wheel-0.1.tar.gz", True),
        ("build/lib/pkg/__init__.py", True),
        ("old_code/index.txt", True),
        ("old_code/pkg/mod.py.bak", True),
        ("logs/server.log", True),
        ("backups/db.dump", True),
        ("data/trash/uuid/file.py", True),
        ("data/versions/deleted.py", True),
        ("src/app.py", False),
        ("lib/README.md", False),
        ("x.lock", True),
        ("dir/foo.log", True),
    ],
)
def test_is_ignored_project_relative_path_defaults(rel: str, expected: bool) -> None:
    """Verify test is ignored project relative path defaults."""
    assert (
        is_ignored_project_relative_path(
            rel,
            include_venv=False,
            include_venv_ignore_exceptions=False,
        )
        is expected
    )


def test_is_ignored_project_relative_path_show_hidden_unignores_cache_and_dot_segments() -> (
    None
):
    """Verify test is ignored project relative path show hidden unignores cache and dot segments."""
    rel = ".mypy_cache/3.12/foo.data.json"
    assert is_ignored_project_relative_path(rel, show_hidden=False) is True
    assert is_ignored_project_relative_path(rel, show_hidden=True) is False
    assert is_ignored_project_relative_path(".cursor/foo.md", show_hidden=True) is False
    assert (
        is_ignored_project_relative_path(
            ".venv/lib/x.py",
            show_hidden=True,
            include_venv=False,
        )
        is True
    )


def test_filter_paths_for_default_project_listing_respects_show_hidden(
    tmp_path: Path,
) -> None:
    """Verify test filter paths for default project listing respects show hidden."""
    root = tmp_path / "proj"
    root.mkdir()
    p = root / ".pytest_cache" / "README.md"
    p.parent.mkdir(parents=True)
    p.write_text("x", encoding="utf-8")
    pr = p.resolve()
    assert (
        filter_paths_for_default_project_listing(
            [pr], root, include_venv=False, include_venv_ignore_exceptions=False
        )
        == []
    )
    assert filter_paths_for_default_project_listing(
        [pr],
        root,
        include_venv=False,
        include_venv_ignore_exceptions=False,
        show_hidden=True,
    ) == [pr]


def test_path_is_under_project_local_venv(tmp_path: Path) -> None:
    """Verify test path is under project local venv."""
    root = tmp_path / "proj"
    root.mkdir()
    inner = root / ".venv" / "lib" / "python3.12" / "site-packages" / "x.py"
    inner.parent.mkdir(parents=True)
    inner.write_text("1")
    assert path_is_under_project_local_venv(inner.resolve(), root)


def test_filter_ignore_exception_py_paths_keeps_allowlisted_venv_file(
    tmp_path: Path,
) -> None:
    """Verify test filter ignore exception py paths keeps allowlisted venv file."""
    root = tmp_path / "proj"
    root.mkdir()
    client = (
        root
        / ".venv"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "mcp_proxy_adapter"
        / "core"
        / "client.py"
    )
    client.parent.mkdir(parents=True)
    client.write_text("x=1")
    cr = client.resolve()
    assert cr in filter_ignore_exception_py_paths_for_watcher(
        {cr}, [root], allowed_venv_py_files={cr}
    )


def test_filter_ignore_exception_py_paths_drops_venv_unless_allowlisted(
    tmp_path: Path,
) -> None:
    """Verify test filter ignore exception py paths drops venv unless allowlisted."""
    root = tmp_path / "proj"
    root.mkdir()
    vpy = root / ".venv" / "lib" / "python3.12" / "site-packages" / "pkg" / "mod.py"
    vpy.parent.mkdir(parents=True)
    vpy.write_text("x=1")
    ok = root / "src" / "app.py"
    ok.parent.mkdir(parents=True)
    ok.write_text("y=1")
    raw = {vpy.resolve(), ok.resolve()}
    out = filter_ignore_exception_py_paths_for_watcher(
        raw, [root], allowed_venv_py_files=None
    )
    assert out == {ok.resolve()}


def test_sql_status_aggregate_fragment_references_venv_and_column() -> None:
    """Verify test sql status aggregate fragment references venv and column."""
    frag = sql_and_absolute_path_eligible_for_default_status_aggregates("files.path")
    assert "files.path" in frag
    assert ".venv" in frag
    assert OLD_CODE_DIR_BASENAME in frag
    assert frag.strip().startswith("AND NOT")


def test_path_matches_traversal_skip_shape_rules() -> None:
    """Verify test path matches traversal skip shape rules."""
    parts = ("home", "proj", "data", "trash", "uuid")
    posix = "/home/proj/data/trash/uuid"
    assert path_matches_traversal_skip_shape_rules(parts, posix) is True
    parts_v = ("home", "proj", "data", "versions", "snap")
    assert (
        path_matches_traversal_skip_shape_rules(
            parts_v, "/home/proj/data/versions/snap"
        )
        is True
    )
    assert (
        path_matches_traversal_skip_shape_rules(
            ("home", "proj", "src"), "/home/proj/src"
        )
        is False
    )


@pytest.mark.parametrize(
    "basename",
    [OLD_CODE_DIR_BASENAME, GIT_DIR_BASENAME, "logs", "backups"],
)
def test_traversal_skip_directory_basenames_include_server_managed(
    basename: str,
) -> None:
    """Verify test traversal skip directory basenames include server managed."""
    from code_analysis.core.project_ignore_policy import (
        DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES,
    )

    assert basename in DEFAULT_TRAVERSAL_SKIP_DIRECTORY_BASENAMES
