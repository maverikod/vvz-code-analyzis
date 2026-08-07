"""
Regression tests for permission-preserving atomic replacement (bug 92e6d693).

The defect: the CST write path staged new content in a ``tempfile.mkstemp``
file (always ``0600``) and ``os.replace``d it over the target. ``os.replace``
is a rename, so the target inherited the staging file's permission bits and an
edited ``.py`` file stopped being readable by anyone but the server.

These tests pin the helper and the three call sites that rename a staged file
over a real project file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from code_analysis.core.atomic_replace import (
    DEFAULT_NEW_FILE_MODE,
    replace_preserving_mode,
)


def _mode(path: Path) -> int:
    """Return the permission bits of ``path``."""
    return stat.S_IMODE(path.stat().st_mode)


def test_replace_keeps_existing_target_mode(tmp_path: Path) -> None:
    """Bug 92e6d693: a 0600 staging file must not make the target 0600."""
    target = tmp_path / "module.py"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o644)

    fd, staged_name = tempfile.mkstemp(dir=tmp_path)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("new\n")
    staged = Path(staged_name)
    assert _mode(staged) == 0o600, "precondition: mkstemp creates 0600"

    replace_preserving_mode(staged, target)

    assert _mode(target) == 0o644
    assert target.read_text(encoding="utf-8") == "new\n"
    assert not staged.exists()


def test_replace_keeps_non_default_target_mode(tmp_path: Path) -> None:
    """An executable target stays executable across a save."""
    target = tmp_path / "script.py"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o755)

    staged = tmp_path / "staged.tmp"
    staged.write_text("new\n", encoding="utf-8")
    os.chmod(staged, 0o600)

    replace_preserving_mode(staged, target)

    assert _mode(target) == 0o755


def test_replace_keeps_restrictive_target_mode(tmp_path: Path) -> None:
    """A deliberately private target is not widened by a save."""
    target = tmp_path / "secret.py"
    target.write_text("old\n", encoding="utf-8")
    os.chmod(target, 0o600)

    staged = tmp_path / "staged.tmp"
    staged.write_text("new\n", encoding="utf-8")
    os.chmod(staged, 0o644)

    replace_preserving_mode(staged, target)

    assert _mode(target) == 0o600


def test_replace_applies_default_mode_for_a_new_target(tmp_path: Path) -> None:
    """With no prior file, the staged file lands with the documented default."""
    target = tmp_path / "created.py"
    fd, staged_name = tempfile.mkstemp(dir=tmp_path)
    os.close(fd)
    staged = Path(staged_name)

    replace_preserving_mode(staged, target)

    assert _mode(target) == DEFAULT_NEW_FILE_MODE


def test_replace_honours_explicit_default_mode(tmp_path: Path) -> None:
    """The new-file default is caller-overridable."""
    target = tmp_path / "created.py"
    staged = tmp_path / "staged.tmp"
    staged.write_text("x\n", encoding="utf-8")

    replace_preserving_mode(staged, target, default_mode=0o600)

    assert _mode(target) == 0o600


def test_replace_still_moves_when_mode_cannot_be_applied(
    tmp_path: Path, monkeypatch
) -> None:
    """A chmod failure is logged, never a reason to lose the write."""
    target = tmp_path / "module.py"
    target.write_text("old\n", encoding="utf-8")
    staged = tmp_path / "staged.tmp"
    staged.write_text("new\n", encoding="utf-8")

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("chmod refused")

    monkeypatch.setattr("code_analysis.core.atomic_replace.os.chmod", _boom)

    replace_preserving_mode(staged, target)

    assert target.read_text(encoding="utf-8") == "new\n"


def test_cst_write_paths_do_not_call_bare_os_replace() -> None:
    """The project-file write paths route through the mode-preserving helper.

    A bare ``os.replace`` at any of these sites is exactly how bug 92e6d693
    happened, so its absence is part of the contract, not a style preference.
    """
    sources = {
        "code_analysis/commands/compose_cst_writer.py",
        "code_analysis/core/cst_tree/tree_saver.py",
        "code_analysis/core/cst_tree/tree_builder_index.py",
    }
    repo_root = Path(__file__).resolve().parent.parent
    for relative in sorted(sources):
        text = (repo_root / relative).read_text(encoding="utf-8")
        assert "replace_preserving_mode(" in text, relative
        assert "os.replace(" not in text, (
            f"{relative} still calls os.replace directly; it must use "
            "replace_preserving_mode so the target keeps its permissions"
        )
