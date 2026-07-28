"""Unit tests for flake8 invocation behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path

from code_analysis.core.code_quality import linter


def test_find_flake8_workdir_uses_nearest_config(tmp_path: Path) -> None:
    """Pick the closest ancestor that owns the flake8 config."""
    repo_root = tmp_path / "repo"
    nested_dir = repo_root / "pkg" / "nested"
    nested_dir.mkdir(parents=True)
    (repo_root / ".flake8").write_text("[flake8]\n", encoding="utf-8")
    file_path = nested_dir / "module.py"
    file_path.write_text("print('x')\n", encoding="utf-8")

    assert linter._find_flake8_workdir(file_path) == repo_root


def test_find_flake8_workdir_falls_back_to_file_parent(tmp_path: Path) -> None:
    """If no config exists, use the file's own parent directory."""
    file_dir = tmp_path / "pkg"
    file_dir.mkdir()
    file_path = file_dir / "module.py"
    file_path.write_text("print('x')\n", encoding="utf-8")

    assert linter._find_flake8_workdir(file_path) == file_dir


def test_lint_with_subprocess_uses_config_workdir_and_no_forced_line_length(
    monkeypatch, tmp_path: Path
) -> None:
    """Invoke flake8 from the config root and let project config drive limits."""
    repo_root = tmp_path / "repo"
    nested_dir = repo_root / "pkg" / "nested"
    nested_dir.mkdir(parents=True)
    (repo_root / ".flake8").write_text("[flake8]\n", encoding="utf-8")
    file_path = nested_dir / "module.py"
    file_path.write_text("print('x')\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="", stderr=""
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    success, error, errors = linter._lint_with_subprocess(file_path)

    assert success is True
    assert error is None
    assert errors == []
    assert "--max-line-length=88" not in captured["cmd"]
    assert captured["cwd"] == repo_root
