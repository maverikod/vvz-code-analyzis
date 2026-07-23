"""
Tests for the ``enumerate_project_paths`` / listing-filter redundant-resolve
elimination (bug 04cb1578, commit 2): ordering and leaf-symlink behavior must be
byte-identical to the pre-optimization always-``.resolve()`` implementation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.ast.list_files import ListProjectFilesMCPCommand
from code_analysis.commands.project_fs_enumerate import enumerate_project_paths


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real DB in unit tests; default index has no file rows."""
    mock_db = MagicMock()
    mock_db.get_project_file_rows.return_value = []

    def _open(_self: object, auto_analyze: bool = False) -> MagicMock:
        """Return the mock DB handle."""
        return mock_db

    monkeypatch.setattr(
        ListProjectFilesMCPCommand, "_open_database_from_config", _open
    )
    monkeypatch.setattr(
        "code_analysis.commands.ast.list_files.get_project_file_rows",
        lambda driver, project_id, include_deleted=False: driver.get_project_file_rows(
            project_id, include_deleted=include_deleted
        ),
    )


def test_ordering_identical_on_mixed_fixture_subdirs_and_dotfiles(
    tmp_path: Path,
) -> None:
    """Sort order over subdirs + dotfiles (show_hidden) must be plain path-sort order."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "b_dir").mkdir()
    (root / "a_dir").mkdir()
    (root / "b_dir" / "z.py").write_text("#\n")
    (root / "b_dir" / "a.py").write_text("#\n")
    (root / "a_dir" / "m.py").write_text("#\n")
    (root / "top.py").write_text("#\n")
    (root / ".dotdir").mkdir()
    (root / ".dotdir" / "hidden.py").write_text("#\n")
    (root / ".dotfile.py").write_text("#\n")

    paths = enumerate_project_paths(
        root, show_venv=False, python_only=False, show_hidden=True
    )
    rels = [p.relative_to(root.resolve()).as_posix() for p in paths]

    assert rels == sorted(rels)
    assert rels == [
        ".dotdir/hidden.py",
        ".dotfile.py",
        "a_dir/m.py",
        "b_dir/a.py",
        "b_dir/z.py",
        "top.py",
    ]


@pytest.mark.asyncio
async def test_ordering_identical_via_list_project_files_command(
    tmp_path: Path,
) -> None:
    """Same ordering guarantee through the full command (pagination-sorted output)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "c.py").write_text("#\n")
    (root / "a.py").write_text("#\n")
    (root / "sub").mkdir()
    (root / "sub" / "b.py").write_text("#\n")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-0000000000e1", page_size=100
        )

    assert result.data is not None
    rels = [f["relative_path"] for f in result.data["files"]]
    assert rels == sorted(rels)
    assert rels == ["a.py", "c.py", "sub/b.py"]


@pytest.mark.skipif(
    not hasattr(os, "symlink"), reason="platform has no symlink support"
)
def test_leaf_symlink_still_resolved_to_real_target(tmp_path: Path) -> None:
    """A leaf symlink file must still be reported (and deduped) at its resolved target.

    Locks in the pre-optimization always-``.resolve()`` behavior: only the leaf-symlink
    case still needs an explicit resolve after the redundant-resolve cleanup (commit 2).
    """
    root = tmp_path / "proj"
    root.mkdir()
    real_dir = root / "data_real"
    real_dir.mkdir()
    target = real_dir / "target.py"
    target.write_text("x = 1\n")

    link = root / "link.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")

    paths = enumerate_project_paths(
        root, show_venv=False, python_only=False, show_hidden=False
    )
    rels = sorted(p.relative_to(root.resolve()).as_posix() for p in paths)

    # The symlink resolves to the same real file already found by the direct
    # walk -- both collapse into exactly one entry, same as the original
    # always-``.resolve()`` implementation (no "link.py" entry survives).
    assert rels == ["data_real/target.py"]


@pytest.mark.skipif(
    not hasattr(os, "symlink"), reason="platform has no symlink support"
)
@pytest.mark.asyncio
async def test_leaf_symlink_via_list_project_files_command(tmp_path: Path) -> None:
    """Full-command leaf-symlink parity: resolved path, deduped, not the link name."""
    root = tmp_path / "proj"
    root.mkdir()
    real_dir = root / "data_real"
    real_dir.mkdir()
    target = real_dir / "target.py"
    target.write_text("x = 1\n")
    link = root / "link.py"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")

    with patch.object(
        ListProjectFilesMCPCommand, "_resolve_project_root", return_value=root
    ):
        cmd = ListProjectFilesMCPCommand()
        result = await cmd.execute(
            project_id="00000000-0000-0000-0000-0000000000e2", page_size=100
        )

    assert result.data is not None
    rels = [f["relative_path"] for f in result.data["files"]]
    assert rels == ["data_real/target.py"]
