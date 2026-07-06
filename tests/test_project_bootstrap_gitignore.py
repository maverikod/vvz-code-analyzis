"""Tests for project .gitignore bootstrap."""

from __future__ import annotations

from pathlib import Path

from code_analysis.core.project_bootstrap.gitignore import GitignoreBootstrap


def test_gitignore_bootstrap_creates_default_file(tmp_path: Path) -> None:
    """Ensure a new project gets a default .gitignore."""
    result = GitignoreBootstrap(tmp_path).ensure()

    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert result.success is True
    assert result.created is True
    assert "__pycache__/" in text
    assert ".venv/" in text
    assert "old_code/" in text
    assert "*.tree" in text
    assert ".cst/" in text
    assert ".trees/" in text


def test_gitignore_bootstrap_appends_missing_without_overwriting(
    tmp_path: Path,
) -> None:
    """Existing user rules are preserved and defaults are appended."""
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("custom.local\nold_code/\n", encoding="utf-8")

    result = GitignoreBootstrap(tmp_path).ensure()
    text = gitignore.read_text(encoding="utf-8")

    assert result.success is True
    assert result.created is False
    assert result.appended
    assert "custom.local\n" in text
    assert text.count("old_code/") == 1
    assert "__pycache__/" in text
    assert "*.tree" in text
