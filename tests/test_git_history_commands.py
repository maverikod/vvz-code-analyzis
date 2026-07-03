"""Tests for advanced git history and tag MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.git_history_commands import (
    GitCherryPickCommand,
    GitCleanCommand,
    GitMergeCommand,
    GitRebaseCommand,
    GitResetCommand,
    GitRevertCommand,
    GitTagCommand,
)
from code_analysis.commands.git_stage_commands import GitAddCommand, GitCommitCommand

PROJECT_ID = "00000000-0000-0000-0000-000000000041"
HISTORY_COMMANDS = (
    GitResetCommand,
    GitCleanCommand,
    GitTagCommand,
    GitMergeCommand,
    GitRebaseCommand,
    GitCherryPickCommand,
    GitRevertCommand,
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


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a small git repository for advanced git command tests."""
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "initial")
    return tmp_path


def test_git_history_command_schema_and_metadata_are_detailed() -> None:
    """Verify advanced command help contracts follow the metadata/schema standard."""
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
    for command_cls in HISTORY_COMMANDS:
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


@pytest.mark.asyncio
async def test_git_reset_unstages_and_requires_hard_confirmation(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_reset can unstage paths and protects hard reset."""
    _patch_root(GitAddCommand, repo, monkeypatch)
    _patch_root(GitResetCommand, repo, monkeypatch)
    (repo / "reset.txt").write_text("reset\n", encoding="utf-8")
    await GitAddCommand().execute(project_id=PROJECT_ID, paths=["reset.txt"])
    assert "A  reset.txt" in _git(repo, "status", "--porcelain=v1")

    result = await GitResetCommand().execute(
        project_id=PROJECT_ID,
        mode="mixed",
        paths=["reset.txt"],
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert "?? reset.txt" in _git(repo, "status", "--porcelain=v1")

    hard_result = await GitResetCommand().execute(
        project_id=PROJECT_ID,
        mode="hard",
        target="HEAD",
    )
    assert isinstance(hard_result, ErrorResult)
    assert hard_result.details["field"] == "confirm_hard"


@pytest.mark.asyncio
async def test_git_clean_dry_run_then_confirmed_delete(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_clean previews by default and deletes only with confirmation."""
    _patch_root(GitCleanCommand, repo, monkeypatch)
    artifact = repo / "artifact.txt"
    artifact.write_text("temp\n", encoding="utf-8")

    preview = await GitCleanCommand().execute(project_id=PROJECT_ID)

    assert isinstance(preview, SuccessResult)
    assert preview.data["dry_run"] is True
    assert "artifact.txt" in preview.data["output"]
    assert artifact.exists()

    deleted = await GitCleanCommand().execute(
        project_id=PROJECT_ID,
        dry_run=False,
        confirm=True,
        paths=["artifact.txt"],
    )

    assert isinstance(deleted, SuccessResult)
    assert deleted.data["dry_run"] is False
    assert not artifact.exists()


@pytest.mark.asyncio
async def test_git_tag_create_list_delete(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify local tag lifecycle."""
    _patch_root(GitTagCommand, repo, monkeypatch)

    create_result = await GitTagCommand().execute(
        project_id=PROJECT_ID,
        action="create",
        name="v-test",
        message="Test tag",
    )
    assert isinstance(create_result, SuccessResult)

    list_result = await GitTagCommand().execute(
        project_id=PROJECT_ID,
        action="list",
        pattern="v-*",
    )
    assert isinstance(list_result, SuccessResult)
    assert list_result.data["tags"] == ["v-test"]

    blocked_delete = await GitTagCommand().execute(
        project_id=PROJECT_ID,
        action="delete",
        name="v-test",
    )
    assert isinstance(blocked_delete, ErrorResult)
    assert blocked_delete.details["field"] == "confirm_delete"

    delete_result = await GitTagCommand().execute(
        project_id=PROJECT_ID,
        action="delete",
        name="v-test",
        confirm_delete=True,
    )
    assert isinstance(delete_result, SuccessResult)
    assert _git(repo, "tag", "--list").strip() == ""


@pytest.mark.asyncio
async def test_git_merge_ff_only(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_merge can fast-forward the current branch."""
    _patch_root(GitMergeCommand, repo, monkeypatch)
    _git(repo, "checkout", "-b", "feature")
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-m", "feature")
    _git(repo, "checkout", "main")

    result = await GitMergeCommand().execute(
        project_id=PROJECT_ID,
        ref="feature",
        ff_only=True,
    )

    assert isinstance(result, SuccessResult)
    assert (repo / "feature.txt").exists()
    assert _git(repo, "log", "-1", "--pretty=%s").strip() == "feature"


@pytest.mark.asyncio
async def test_git_cherry_pick_no_commit(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_cherry_pick can apply a commit without committing it."""
    _patch_root(GitCherryPickCommand, repo, monkeypatch)
    _git(repo, "checkout", "-b", "source")
    (repo / "picked.txt").write_text("picked\n", encoding="utf-8")
    _git(repo, "add", "picked.txt")
    _git(repo, "commit", "-m", "picked")
    commit = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "main")

    result = await GitCherryPickCommand().execute(
        project_id=PROJECT_ID,
        commits=[commit],
        no_commit=True,
    )

    assert isinstance(result, SuccessResult)
    assert "A  picked.txt" in _git(repo, "status", "--porcelain=v1")


@pytest.mark.asyncio
async def test_git_rebase_current_branch(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_rebase can replay the current branch onto another branch."""
    _patch_root(GitRebaseCommand, repo, monkeypatch)
    _git(repo, "checkout", "-b", "feature")
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-m", "feature")
    feature_commit_before = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "main")
    (repo / "main.txt").write_text("main\n", encoding="utf-8")
    _git(repo, "add", "main.txt")
    _git(repo, "commit", "-m", "main advance")
    main_commit = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "feature")

    result = await GitRebaseCommand().execute(
        project_id=PROJECT_ID,
        upstream="main",
    )

    assert isinstance(result, SuccessResult)
    assert _git(repo, "rev-parse", "HEAD~1").strip() == main_commit
    assert _git(repo, "rev-parse", "HEAD").strip() != feature_commit_before


@pytest.mark.asyncio
async def test_git_revert_no_commit(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify git_revert can apply inverse changes without committing."""
    _patch_root(GitRevertCommand, repo, monkeypatch)
    readme = repo / "README.md"
    readme.write_text("changed\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "change readme")
    commit = _git(repo, "rev-parse", "HEAD").strip()

    result = await GitRevertCommand().execute(
        project_id=PROJECT_ID,
        commits=[commit],
        no_commit=True,
    )

    assert isinstance(result, SuccessResult)
    assert readme.read_text(encoding="utf-8") == "initial\n"
    assert "M  README.md" in _git(repo, "status", "--porcelain=v1")
