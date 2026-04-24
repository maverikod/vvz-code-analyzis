"""Tests for file_management.path_mask_match."""

from pathlib import Path

from code_analysis.commands.file_management.path_mask_match import (
    filter_rows_by_mask,
    normalize_path_mask_for_project,
    path_matches_mask,
    relative_path_posix,
)


def test_normalize_leading_slash_project_root() -> None:
    assert normalize_path_mask_for_project("/build") == "build"
    assert normalize_path_mask_for_project("///build/") == "build/"
    assert normalize_path_mask_for_project("\\build\\x") == "build/x"


def test_star_and_slash_star_masks_equivalent() -> None:
    """Leading / is project-root only; * and /* denote the same pattern."""
    assert normalize_path_mask_for_project("*") == normalize_path_mask_for_project("/*")
    assert normalize_path_mask_for_project("*") == normalize_path_mask_for_project("//*")
    assert normalize_path_mask_for_project("tests/**/*.py") == normalize_path_mask_for_project(
        "/tests/**/*.py"
    )
    assert path_matches_mask("foo.py", "*") is path_matches_mask("foo.py", "/*")
    assert path_matches_mask("pkg/x.py", "tests/**/*.py") == path_matches_mask(
        "pkg/x.py", "/tests/**/*.py"
    )


def test_prefix_mask_directory_tree() -> None:
    assert path_matches_mask("pkg/sub/foo.py", "pkg/sub")
    assert path_matches_mask("pkg/sub/foo.py", "/pkg/sub")
    assert path_matches_mask("pkg/sub/foo.py", "pkg/sub/")
    assert path_matches_mask("pkg/sub", "pkg/sub")
    assert not path_matches_mask("pkg/other/x.py", "pkg/sub")


def test_rm_style_first_path_component() -> None:
    assert path_matches_mask("testing/deep/x.py", "/tes*")
    assert path_matches_mask("tes.py", "tes*")
    assert not path_matches_mask("src/tes.py", "/tes*")
    assert not path_matches_mask("src/testing/x.py", "/tes*")


def test_glob_double_star() -> None:
    assert path_matches_mask("tests/unit/a.py", "tests/**/*.py")
    assert not path_matches_mask("src/a.py", "tests/**/*.py")


def test_glob_single_segment() -> None:
    assert path_matches_mask("foo.py", "*.py")
    assert not path_matches_mask("dir/foo.py", "*.py")


def test_relative_path_posix(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "a").mkdir(parents=True)
    f = root / "a" / "b.py"
    f.write_text("x")
    rel = relative_path_posix(root, str(f))
    assert rel == "a/b.py"


def test_filter_rows_by_mask(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    p1 = (root / "keep.py").resolve()
    p2 = (root / "drop" / "x.py").resolve()
    p2.parent.mkdir(parents=True)
    p1.write_text("1")
    p2.write_text("2")
    rows = [
        {"path": str(p1), "id": 1},
        {"path": str(p2), "id": 2},
    ]
    out = filter_rows_by_mask(rows, root, "drop")
    assert len(out) == 1
    assert out[0]["id"] == 2
