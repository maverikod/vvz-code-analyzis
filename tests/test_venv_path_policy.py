"""
Tests for venv path policy (index allowlist + write guards).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from code_analysis.core.file_watcher_pkg.scanner import should_ignore_path
from unittest.mock import patch

from code_analysis.core.venv_path_policy import (
    build_allowlisted_site_packages_py_files,
    collect_python_files_for_indexing,
    expand_ignore_exception_all_files,
    expand_ignore_exception_py_files,
    format_project_venv_write_forbidden_message,
    iter_project_files_excluding_venv,
    load_ignore_exceptions_from_config_path,
    normalize_pep503_distribution_name,
    path_is_under_project_local_venv,
)


def test_normalize_pep503_distribution_name() -> None:
    """Verify test normalize pep503 distribution name."""
    assert normalize_pep503_distribution_name("Some_Package") == "some-package"
    assert normalize_pep503_distribution_name("requests") == "requests"


def test_path_is_under_project_local_venv(tmp_path: Path) -> None:
    """Verify test path is under project local venv."""
    root = tmp_path / "proj"
    root.mkdir()
    py = root / ".venv" / "lib" / "python3.12" / "site-packages" / "x.py"
    py.parent.mkdir(parents=True)
    py.write_text("#\n")
    assert path_is_under_project_local_venv(py, root) is True
    assert path_is_under_project_local_venv(root / "src" / "main.py", root) is False


def test_build_allowlisted_site_packages_py_files_from_record(tmp_path: Path) -> None:
    """Verify test build allowlisted site packages py files from record."""
    root = tmp_path / "proj"
    sp = root / ".venv" / "lib" / "python3.12" / "site-packages"
    sp.mkdir(parents=True)
    pkg_dir = sp / "mypkg"
    pkg_dir.mkdir()
    (pkg_dir / "mod.py").write_text("x = 1\n", encoding="utf-8")
    dist = sp / "mypkg-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: mypkg\nVersion: 1.0\n")
    (dist / "RECORD").write_text("mypkg/mod.py,sha256=abc,12\n", encoding="utf-8")

    found = build_allowlisted_site_packages_py_files(root, ["mypkg"])
    assert (pkg_dir / "mod.py").resolve() in found
    assert build_allowlisted_site_packages_py_files(root, ["other-dist"]) == frozenset()


def test_collect_python_files_for_indexing_merges(tmp_path: Path) -> None:
    """Verify test collect python files for indexing merges."""
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("a = 1\n")
    sp = root / ".venv" / "lib" / "python3.12" / "site-packages"
    sp.mkdir(parents=True)
    pkg_dir = sp / "dep"
    pkg_dir.mkdir()
    (pkg_dir / "x.py").write_text("b = 2\n")
    dist = sp / "dep-0.1.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Name: dep\nVersion: 0.1\n")
    (dist / "RECORD").write_text("dep/x.py,sha256=ab,1\n", encoding="utf-8")

    only_proj = collect_python_files_for_indexing(root, [])
    assert (root / "src" / "app.py") in only_proj
    assert not any(".venv" in str(p) for p in only_proj)

    merged = collect_python_files_for_indexing(root, ["dep"])
    assert (root / "src" / "app.py") in merged
    assert (pkg_dir / "x.py").resolve() in merged


def test_expand_ignore_exception_py_files_under_venv(tmp_path: Path) -> None:
    """Verify test expand ignore exception py files under venv."""
    root = tmp_path / "proj"
    vpy = root / ".venv" / "lib" / "python3.12" / "site-packages" / "pkg" / "keep.py"
    vpy.parent.mkdir(parents=True)
    vpy.write_text("x = 1\n")
    found = expand_ignore_exception_py_files(
        root, [".venv/lib/**/site-packages/pkg/**/*.py"]
    )
    assert vpy.resolve() in found


def test_collect_python_files_for_indexing_does_not_merge_venv_ignore_exceptions(
    tmp_path: Path,
) -> None:
    """Verify test collect python files for indexing does not merge venv ignore exceptions."""
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("a = 1\n")
    vpy = root / ".venv" / "extra" / "forced.py"
    vpy.parent.mkdir(parents=True)
    vpy.write_text("FORCED = 1\n")
    with patch(
        "code_analysis.core.venv_path_policy.load_ignore_exceptions_from_config",
        return_value=[".venv/extra/*.py"],
    ):
        files = collect_python_files_for_indexing(root, [])
    assert (root / "src" / "app.py") in files
    assert vpy.resolve() not in files


def test_load_ignore_exceptions_from_explicit_config_path(tmp_path: Path) -> None:
    """Verify test load ignore exceptions from explicit config path."""
    cfg = tmp_path / "config.json"
    cfg.write_text(
        (
            '{"code_analysis": {"ignore_exceptions": '
            '["**/src/generated/keep.py", "**/pkg/special/**"]}}'
        ),
        encoding="utf-8",
    )
    assert load_ignore_exceptions_from_config_path(cfg) == [
        "**/src/generated/keep.py",
        "**/pkg/special/**",
    ]


def test_should_ignore_path_respects_allowlisted_venv_file(tmp_path: Path) -> None:
    """Verify test should ignore path respects allowlisted venv file."""
    root = tmp_path / "p"
    root.mkdir()
    vpy = root / ".venv" / "lib" / "python3.12" / "site-packages" / "pkg" / "a.py"
    vpy.parent.mkdir(parents=True)
    vpy.write_text("#\n")
    resolved = {vpy.resolve()}
    rr = root.resolve()
    assert (
        should_ignore_path(vpy, allowed_venv_py_files=resolved, project_root=rr)
        is False
    )
    assert should_ignore_path(vpy, allowed_venv_py_files=None, project_root=rr) is True
    assert (
        should_ignore_path(
            vpy,
            ignore_exception_files={vpy.resolve()},
            project_root=rr,
        )
        is True
    )
    assert (
        should_ignore_path(
            vpy,
            ignore_exception_files={vpy.resolve()},
            allowed_venv_py_files=resolved,
            project_root=rr,
        )
        is False
    )


def test_format_message_non_empty() -> None:
    """Verify test format message non empty."""
    assert "read-only" in format_project_venv_write_forbidden_message().lower()


def test_iter_project_files_excluding_venv_skips_pyc(tmp_path: Path) -> None:
    """Verify test iter project files excluding venv skips pyc."""
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("a = 1\n")
    (root / "src" / "mod.pyc").write_bytes(b"\0")

    found = iter_project_files_excluding_venv(root)
    assert (root / "src" / "app.py") in found
    assert not any(p.name == "mod.pyc" for p in found)


def test_iter_project_files_excluding_venv_show_hidden_descends_mypy_and_dot_dir(
    tmp_path: Path,
) -> None:
    """Verify test iter project files excluding venv show hidden descends mypy and dot dir."""
    root = tmp_path / "proj"
    root.mkdir()
    cache_dir = root / ".mypy_cache" / "3.12"
    cache_dir.mkdir(parents=True)
    marker = cache_dir / "data.json"
    marker.write_text("{}", encoding="utf-8")
    dot_dir = root / ".github" / "workflows"
    dot_dir.mkdir(parents=True)
    wf = dot_dir / "ci.yml"
    wf.write_text("on: {}\n", encoding="utf-8")
    found_default = iter_project_files_excluding_venv(root)
    assert not any(".mypy_cache" in p.as_posix() for p in found_default)
    assert not any(".github" in p.as_posix() for p in found_default)
    found_hidden = iter_project_files_excluding_venv(root, show_hidden=True)
    assert marker.resolve() in [p.resolve() for p in found_hidden]
    assert wf.resolve() in [p.resolve() for p in found_hidden]


def test_expand_ignore_exception_all_files_includes_non_py(tmp_path: Path) -> None:
    """Verify test expand ignore exception all files includes non py."""
    root = tmp_path / "proj"
    root.mkdir()
    vdir = root / ".venv"
    vdir.mkdir()
    (vdir / "note.md").write_text("x\n", encoding="utf-8")

    py_only = expand_ignore_exception_py_files(root, [".venv/*.md"])
    assert list(py_only) == []

    all_files = expand_ignore_exception_all_files(root, [".venv/*.md"])
    assert (vdir / "note.md").resolve() in all_files
