"""Unit tests for :mod:`code_analysis.core.project_ignore_policy`."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.core.project_ignore_policy import (
    filter_ignore_exception_py_paths_for_watcher,
    is_ignored_project_relative_path,
    path_is_under_project_local_venv,
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
        ("src/app.py", False),
        ("lib/README.md", False),
        ("x.lock", True),
        ("dir/foo.log", True),
    ],
)
def test_is_ignored_project_relative_path_defaults(rel: str, expected: bool) -> None:
    assert (
        is_ignored_project_relative_path(
            rel,
            include_venv=False,
            include_venv_ignore_exceptions=False,
        )
        is expected
    )


def test_path_is_under_project_local_venv(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    inner = root / ".venv" / "lib" / "python3.12" / "site-packages" / "x.py"
    inner.parent.mkdir(parents=True)
    inner.write_text("1")
    assert path_is_under_project_local_venv(inner.resolve(), root)


def test_filter_ignore_exception_py_paths_keeps_allowlisted_venv_file(
    tmp_path: Path,
) -> None:
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
    frag = sql_and_absolute_path_eligible_for_default_status_aggregates("files.path")
    assert "files.path" in frag
    assert ".venv" in frag
    assert frag.strip().startswith("AND NOT")
