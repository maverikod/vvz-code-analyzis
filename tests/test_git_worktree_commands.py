"""
Tests for git working-tree MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.git_worktree_commands import (
    GitAddCommand,
    GitCommitCommand,
    GitInitCommand,
    GitRestoreCommand,
    GitStashApplyCommand,
    GitStashDropCommand,
    GitStashListCommand,
    GitStashPushCommand,
)

PROJECT_ID = "00000000-0000-0000-0000-000000000031"
WORKTREE_COMMANDS = (
    GitAddCommand,
    GitCommitCommand,
    GitInitCommand,
    GitRestoreCommand,
    GitStashPushCommand,
    GitStashListCommand,
    GitStashApplyCommand,
    GitStashDropCommand,
)


def _git(cwd: Path, *args: str) -> str:
    """Run git in cwd and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _patch_root(command_cls: type, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch a command class to resolve PROJECT_ID to repo."""
    monkeypatch.setattr(
        command_cls,
        "_resolve_project_root",
        lambda _self, _project_id: repo,
    )


def test_git_worktree_command_schema_and_metadata_are_detailed() -> None:
    """Verify new command help contracts follow the metadata/schema standard."""
    required_metadata_keys = {
        "name",
        "version",
        "description",
        "category",
        "author",
        "email",
        "detailed_description",
        "parameters",
        "return_value",
        "usage_examples",
        "error_cases",
        "best_practices",
    }
    for command_cls in WORKTREE_COMMANDS:
        schema = command_cls.get_schema()
        metadata = command_cls.metadata()
        missing = required_metadata_keys - set(metadata)
        assert missing == set(), f"{command_cls.name} missing metadata keys: {missing}"
        assert schema["additionalProperties"] is False
        assert metadata["name"] == command_cls.name
        assert metadata["version"] == command_cls.version
        assert metadata["description"] == command_cls.descr
        assert len(metadata["detailed_description"]) > 500
        assert metadata["usage_examples"]
        assert metadata["error_cases"]
        assert metadata["best_practices"]
        assert "success" in metadata["return_value"]
        assert "error" in metadata["return_value"]
        for param_name, param_schema in schema["properties"].items():
            assert param_schema.get(
                "description"
            ), f"{command_cls.name}.{param_name} lacks schema description"
            assert param_name in metadata["parameters"]
            assert metadata["parameters"][param_name].get("description")
            assert "required" in metadata["parameters"][param_name]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a small git repository for working-tree command tests."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "initial")
    return tmp_path


@pytest.mark.asyncio
async def test_git_add_stages_selected_paths(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_add stages selected paths only."""
    _patch_root(GitAddCommand, repo, monkeypatch)
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    result = await GitAddCommand().execute(
        project_id=PROJECT_ID,
        paths=["tracked.txt"],
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    status = _git(repo, "status", "--porcelain=v1")
    assert "A  tracked.txt" in status
    assert "?? untracked.txt" in status


@pytest.mark.asyncio
async def test_git_init_creates_missing_path(tmp_path: Path) -> None:
    """Verify git_init follows git init behavior for a missing path."""
    target = tmp_path / "new_repo"

    result = await GitInitCommand().execute(path=str(target))

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["path"] == str(target)
    assert (target / ".git").is_dir()


@pytest.mark.asyncio
async def test_git_init_reinitializes_existing_repo(repo: Path) -> None:
    """Verify git_init succeeds when the path is already a repository."""
    result = await GitInitCommand().execute(path=str(repo))

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["path"] == str(repo)
    assert (repo / ".git").is_dir()


@pytest.mark.asyncio
async def test_git_commit_creates_commit_from_staged_changes(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_commit commits staged changes."""
    _patch_root(GitAddCommand, repo, monkeypatch)
    _patch_root(GitCommitCommand, repo, monkeypatch)
    (repo / "commit.txt").write_text("commit\n", encoding="utf-8")
    await GitAddCommand().execute(project_id=PROJECT_ID, paths=["commit.txt"])

    result = await GitCommitCommand().execute(
        project_id=PROJECT_ID,
        message="add commit file",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["commit"]
    assert _git(repo, "log", "-1", "--pretty=%s").strip() == "add commit file"
    assert _git(repo, "status", "--porcelain=v1").strip() == ""


@pytest.mark.asyncio
async def test_git_restore_can_unstage_without_touching_worktree(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_restore with staged=true/worktree=false unstages changes."""
    _patch_root(GitAddCommand, repo, monkeypatch)
    _patch_root(GitRestoreCommand, repo, monkeypatch)
    readme = repo / "README.md"
    readme.write_text("changed\n", encoding="utf-8")
    await GitAddCommand().execute(project_id=PROJECT_ID, paths=["README.md"])

    result = await GitRestoreCommand().execute(
        project_id=PROJECT_ID,
        paths=["README.md"],
        staged=True,
        worktree=False,
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    status = _git(repo, "status", "--porcelain=v1")
    assert " M README.md" in status
    assert readme.read_text(encoding="utf-8") == "changed\n"


@pytest.mark.asyncio
async def test_git_restore_can_discard_worktree_change(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_restore restores a worktree file from HEAD."""
    _patch_root(GitRestoreCommand, repo, monkeypatch)
    readme = repo / "README.md"
    readme.write_text("discard me\n", encoding="utf-8")

    result = await GitRestoreCommand().execute(
        project_id=PROJECT_ID,
        paths=["README.md"],
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert readme.read_text(encoding="utf-8") == "initial\n"
    assert _git(repo, "status", "--porcelain=v1").strip() == ""


@pytest.mark.asyncio
async def test_git_stash_push_list_apply_and_drop(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the basic stash workflow."""
    for command_cls in (
        GitStashPushCommand,
        GitStashListCommand,
        GitStashApplyCommand,
        GitStashDropCommand,
        GitRestoreCommand,
    ):
        _patch_root(command_cls, repo, monkeypatch)
    readme = repo / "README.md"
    readme.write_text("stashed\n", encoding="utf-8")

    push_result = await GitStashPushCommand().execute(
        project_id=PROJECT_ID,
        message="save readme",
    )
    assert isinstance(push_result, SuccessResult)
    assert push_result.data["success"] is True
    assert readme.read_text(encoding="utf-8") == "initial\n"

    list_result = await GitStashListCommand().execute(project_id=PROJECT_ID)
    assert isinstance(list_result, SuccessResult)
    assert list_result.data["count"] == 1
    assert "save readme" in list_result.data["entries"][0]["summary"]

    apply_result = await GitStashApplyCommand().execute(project_id=PROJECT_ID)
    assert isinstance(apply_result, SuccessResult)
    assert apply_result.data["success"] is True
    assert readme.read_text(encoding="utf-8") == "stashed\n"

    await GitRestoreCommand().execute(
        project_id=PROJECT_ID,
        paths=["README.md"],
    )
    drop_result = await GitStashDropCommand().execute(project_id=PROJECT_ID)
    assert isinstance(drop_result, SuccessResult)
    assert drop_result.data["success"] is True
    assert _git(repo, "stash", "list").strip() == ""
