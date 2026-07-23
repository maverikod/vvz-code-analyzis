"""
``git_pull_safe`` content_stale marking (bug 56c23bd9): the pull path rewrites
file content on disk directly, bypassing every other CA write path, so it must
mark its own changed files stale.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

from code_analysis.commands.git_admin_commands import (
    _git_rev_parse_head,
    _mark_pull_changed_files_stale,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.com",
            "PATH": "/usr/bin:/bin",
        },
    )


def _make_two_commit_repo(tmp_path: Path) -> Tuple[Path, str, str]:
    """Create a repo with two commits differing by one changed file."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "a.py").write_text("print('one')\n")
    (root / "untouched.py").write_text("print('same')\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "c1")
    pre_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()

    (root / "a.py").write_text("print('two')\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "c2")
    post_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    return root, pre_head, post_head


class _FakeDb:
    def __init__(self) -> None:
        self.execute_calls: List[Tuple[str, Optional[tuple]]] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        self.execute_calls.append((sql, params))
        return {}


def test_git_rev_parse_head_reads_current_commit(tmp_path: Path) -> None:
    """_git_rev_parse_head: returns the current HEAD sha."""
    root, _pre, post = _make_two_commit_repo(tmp_path)
    assert _git_rev_parse_head(root) == post


def test_git_rev_parse_head_returns_none_when_not_a_repo(tmp_path: Path) -> None:
    """_git_rev_parse_head: non-repo directory -> None, not an exception."""
    plain_dir = tmp_path / "not_a_repo"
    plain_dir.mkdir()
    assert _git_rev_parse_head(plain_dir) is None


def test_mark_pull_changed_files_stale_marks_only_changed_paths(
    tmp_path: Path,
) -> None:
    """Per-file mode: only the file the pull actually changed gets marked."""
    root, pre_head, post_head = _make_two_commit_repo(tmp_path)
    fake_db = _FakeDb()
    marked_calls: List[Tuple[str, str]] = []

    def _fake_mark(driver: Any, file_path: str, project_id: str) -> bool:
        marked_calls.append((file_path, project_id))
        return True

    with patch(
        "code_analysis.commands.base_mcp_command.BaseMCPCommand._open_database_from_config",
        return_value=fake_db,
    ), patch(
        "code_analysis.core.database_driver_pkg.domain.files.mark_file_content_stale",
        side_effect=_fake_mark,
    ):
        result = _mark_pull_changed_files_stale(root, "proj-1", pre_head, post_head)

    assert result["mode"] == "per_file"
    assert result["marked"] == 1
    assert len(marked_calls) == 1
    marked_path, marked_project = marked_calls[0]
    assert marked_path.endswith("a.py")
    assert marked_project == "proj-1"


def test_mark_pull_changed_files_stale_no_change_is_a_noop() -> None:
    """pre_head == post_head (no-op pull) -> no marking, no DB call."""
    with patch(
        "code_analysis.commands.base_mcp_command.BaseMCPCommand._open_database_from_config",
    ) as open_db:
        result = _mark_pull_changed_files_stale(
            Path("/nonexistent"), "proj-1", "same-sha", "same-sha"
        )

    assert result == {"marked": 0, "mode": "no_change"}
    open_db.assert_called_once()


def test_mark_pull_changed_files_stale_falls_back_project_wide_on_diff_failure(
    tmp_path: Path,
) -> None:
    """diff --name-only failing (e.g. unresolvable head) -> project-wide UPDATE fallback."""
    root = tmp_path / "not_a_repo"
    root.mkdir()
    fake_db = _FakeDb()

    with patch(
        "code_analysis.commands.base_mcp_command.BaseMCPCommand._open_database_from_config",
        return_value=fake_db,
    ):
        result = _mark_pull_changed_files_stale(
            root, "proj-1", "deadbeef", "cafef00d"
        )

    assert result["mode"] == "project_wide"
    assert len(fake_db.execute_calls) == 1
    sql, params = fake_db.execute_calls[0]
    assert "content_stale = 1" in sql
    assert params == ("proj-1",)
