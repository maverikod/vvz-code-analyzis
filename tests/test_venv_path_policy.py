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
    expand_ignore_exception_py_files,
    format_project_venv_write_forbidden_message,
    normalize_pep503_distribution_name,
    path_is_under_project_local_venv,
)


def test_normalize_pep503_distribution_name() -> None:
    assert normalize_pep503_distribution_name("Some_Package") == "some-package"
    assert normalize_pep503_distribution_name("requests") == "requests"


def test_path_is_under_project_local_venv(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    py = root / ".venv" / "lib" / "python3.12" / "site-packages" / "x.py"
    py.parent.mkdir(parents=True)
    py.write_text("#\n")
    assert path_is_under_project_local_venv(py, root) is True
    assert path_is_under_project_local_venv(root / "src" / "main.py", root) is False


def test_build_allowlisted_site_packages_py_files_from_record(tmp_path: Path) -> None:
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
    root = tmp_path / "proj"
    vpy = root / ".venv" / "lib" / "python3.12" / "site-packages" / "pkg" / "keep.py"
    vpy.parent.mkdir(parents=True)
    vpy.write_text("x = 1\n")
    found = expand_ignore_exception_py_files(
        root, [".venv/lib/**/site-packages/pkg/**/*.py"]
    )
    assert vpy.resolve() in found


def test_collect_python_files_for_indexing_merges_ignore_exceptions(
    tmp_path: Path,
) -> None:
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
    assert vpy.resolve() in files


def test_should_ignore_path_respects_allowlisted_venv_file(tmp_path: Path) -> None:
    root = tmp_path / "p"
    vpy = root / ".venv" / "lib" / "python3.12" / "site-packages" / "pkg" / "a.py"
    vpy.parent.mkdir(parents=True)
    vpy.write_text("#\n")
    resolved = {vpy.resolve()}
    assert should_ignore_path(vpy, allowed_venv_py_files=resolved) is False
    assert should_ignore_path(vpy, allowed_venv_py_files=None) is True
    assert should_ignore_path(vpy, ignore_exception_files={vpy.resolve()}) is False


def test_format_message_non_empty() -> None:
    assert "read-only" in format_project_venv_write_forbidden_message().lower()
