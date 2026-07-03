"""
Tests for project-scoped git branch MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.git_branch_checkout_command import GitBranchCheckoutCommand
from code_analysis.commands.git_branch_create_command import GitBranchCreateCommand
from code_analysis.commands.git_branch_delete_command import GitBranchDeleteCommand
from code_analysis.commands.git_branch_delete_remote_command import (
    GitBranchDeleteRemoteCommand,
)
from code_analysis.commands.git_branch_fetch_pull_commands import (
    GitBranchFetchCommand,
    GitBranchPullCommand,
)
from code_analysis.commands.git_branch_push_command import GitBranchPushCommand
from code_analysis.commands.git_branch_track_remote_command import (
    GitBranchTrackRemoteCommand,
)
from code_analysis.commands.git_branch_upstream_commands import (
    GitBranchSetUpstreamCommand,
    GitBranchUnsetUpstreamCommand,
)
from code_analysis.commands.git_ops.git_branch_current_command import (
    GitBranchCurrentCommand,
)
from code_analysis.commands.git_ops.git_branch_compare_command import (
    GitBranchCompareCommand,
)
from code_analysis.commands.git_ops.git_branch_list_command import GitBranchListCommand
from code_analysis.commands.git_ops.git_branch_sync_status_command import (
    GitBranchSyncStatusCommand,
)

PROJECT_ID = "00000000-0000-0000-0000-000000000021"


def _remote_config() -> dict:
    """Return test config enabling remote git commands."""
    return {
        "code_analysis": {
            "git": {
                "remote_enabled": True,
                "protected_branches": [],
                "allow_force_push": False,
                "remote_timeout_seconds": 30,
            }
        }
    }


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


@pytest.fixture
def repo_with_remote(tmp_path: Path) -> Path:
    """Create a small repository with local and remote-tracking branches."""
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(tmp_path, "clone", str(remote), str(repo))
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("main\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "branch", "-M", "main")
    _git(repo, "push", "-u", "origin", "main")
    _git(repo, "checkout", "-b", "feature/local")
    (repo / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-m", "feature")
    _git(repo, "push", "-u", "origin", "feature/local")
    _git(repo, "checkout", "main")
    return repo


@pytest.mark.asyncio
async def test_git_branch_list_all_scopes(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify branch list returns local and remote branches."""
    monkeypatch.setattr(
        GitBranchListCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    result = await GitBranchListCommand().execute(project_id=PROJECT_ID)

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["available"] is True
    names = {branch["name"]: branch for branch in result.data["branches"]}
    assert "main" in names
    assert "feature/local" in names
    assert "origin/main" in names
    assert "origin/feature/local" in names
    assert names["main"]["current"] is True
    assert names["origin/main"]["scope"] == "remote"
    assert names["origin/main"]["remote"] == "origin"


@pytest.mark.asyncio
async def test_git_branch_list_remote_scope(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify remote scope excludes local branches."""
    monkeypatch.setattr(
        GitBranchListCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    result = await GitBranchListCommand().execute(
        project_id=PROJECT_ID,
        scope="remote",
    )

    assert isinstance(result, SuccessResult)
    names = {branch["name"] for branch in result.data["branches"]}
    assert names == {"origin/main", "origin/feature/local"}
    assert result.data["scope"] == "remote"


@pytest.mark.asyncio
async def test_git_branch_current_reports_upstream_counts(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify current branch command reports upstream sync state."""
    monkeypatch.setattr(
        GitBranchCurrentCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    result = await GitBranchCurrentCommand().execute(project_id=PROJECT_ID)

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["available"] is True
    assert result.data["branch"] == "main"
    assert result.data["upstream"] == "origin/main"
    assert result.data["ahead"] == 0
    assert result.data["behind"] == 0
    assert result.data["detached"] is False


@pytest.mark.asyncio
async def test_git_branch_create_creates_local_branch(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify branch create command creates a local branch without checkout."""
    monkeypatch.setattr(
        GitBranchCreateCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    result = await GitBranchCreateCommand().execute(
        project_id=PROJECT_ID,
        name="feature/created",
        start_point="main",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["name"] == "feature/created"
    branches = _git(repo_with_remote, "branch", "--list", "feature/created")
    assert "feature/created" in branches
    assert _git(repo_with_remote, "branch", "--show-current").strip() == "main"


@pytest.mark.asyncio
async def test_git_branch_checkout_switches_branch(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify branch checkout switches to an existing branch."""
    monkeypatch.setattr(
        GitBranchCheckoutCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    result = await GitBranchCheckoutCommand().execute(
        project_id=PROJECT_ID,
        name="feature/local",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["created"] is False
    assert _git(repo_with_remote, "branch", "--show-current").strip() == "feature/local"


@pytest.mark.asyncio
async def test_git_branch_delete_deletes_local_branch(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify branch delete removes a local branch."""
    _git(repo_with_remote, "branch", "feature/delete-me", "main")
    monkeypatch.setattr(
        GitBranchDeleteCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    result = await GitBranchDeleteCommand().execute(
        project_id=PROJECT_ID,
        name="feature/delete-me",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    branches = _git(repo_with_remote, "branch", "--list", "feature/delete-me")
    assert branches.strip() == ""


@pytest.mark.asyncio
async def test_git_branch_set_and_unset_upstream(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify upstream commands update local tracking config."""
    _git(repo_with_remote, "branch", "--unset-upstream", "feature/local")
    monkeypatch.setattr(
        GitBranchSetUpstreamCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )
    monkeypatch.setattr(
        GitBranchUnsetUpstreamCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    set_result = await GitBranchSetUpstreamCommand().execute(
        project_id=PROJECT_ID,
        branch="feature/local",
        upstream="origin/feature/local",
    )

    assert isinstance(set_result, SuccessResult)
    assert set_result.data["success"] is True
    upstream = _git(
        repo_with_remote,
        "rev-parse",
        "--abbrev-ref",
        "feature/local@{upstream}",
    ).strip()
    assert upstream == "origin/feature/local"

    unset_result = await GitBranchUnsetUpstreamCommand().execute(
        project_id=PROJECT_ID,
        branch="feature/local",
    )

    assert isinstance(unset_result, SuccessResult)
    assert unset_result.data["success"] is True
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "feature/local@{upstream}"],
        cwd=str(repo_with_remote),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


@pytest.mark.asyncio
async def test_git_branch_push_pushes_branch_to_remote(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify branch push sends a local branch to the remote."""
    _git(repo_with_remote, "checkout", "-b", "feature/push-me", "main")
    (repo_with_remote / "push.txt").write_text("push\n", encoding="utf-8")
    _git(repo_with_remote, "add", "push.txt")
    _git(repo_with_remote, "commit", "-m", "push branch")
    monkeypatch.setattr(
        GitBranchPushCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )
    monkeypatch.setattr(
        GitBranchPushCommand,
        "_get_raw_config",
        staticmethod(_remote_config),
    )
    monkeypatch.setattr(
        "code_analysis.commands.git_branch_push_command.build_full_subprocess_env",
        lambda _config: (None, None),
    )

    result = await GitBranchPushCommand().execute(
        project_id=PROJECT_ID,
        branch="feature/push-me",
        set_upstream=True,
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    refs = _git(repo_with_remote, "ls-remote", "--heads", "origin", "feature/push-me")
    assert "refs/heads/feature/push-me" in refs
    upstream = _git(
        repo_with_remote,
        "rev-parse",
        "--abbrev-ref",
        "feature/push-me@{upstream}",
    ).strip()
    assert upstream == "origin/feature/push-me"


@pytest.mark.asyncio
async def test_git_branch_delete_remote_deletes_remote_branch(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify remote branch delete removes a branch from origin."""
    _git(repo_with_remote, "checkout", "-b", "feature/delete-remote", "main")
    (repo_with_remote / "remote-delete.txt").write_text("delete\n", encoding="utf-8")
    _git(repo_with_remote, "add", "remote-delete.txt")
    _git(repo_with_remote, "commit", "-m", "remote delete branch")
    _git(repo_with_remote, "push", "-u", "origin", "feature/delete-remote")
    monkeypatch.setattr(
        GitBranchDeleteRemoteCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )
    monkeypatch.setattr(
        GitBranchDeleteRemoteCommand,
        "_get_raw_config",
        staticmethod(_remote_config),
    )
    monkeypatch.setattr(
        "code_analysis.commands.git_branch_delete_remote_command.build_full_subprocess_env",
        lambda _config: (None, None),
    )

    result = await GitBranchDeleteRemoteCommand().execute(
        project_id=PROJECT_ID,
        branch="feature/delete-remote",
        force_confirm=True,
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    refs = _git(
        repo_with_remote, "ls-remote", "--heads", "origin", "feature/delete-remote"
    )
    assert refs.strip() == ""


@pytest.mark.asyncio
async def test_git_branch_fetch_fetches_named_branch(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify branch fetch updates remote-tracking refs."""
    other = repo_with_remote.parent / "other"
    _git(
        repo_with_remote.parent,
        "clone",
        str(repo_with_remote.parent / "remote.git"),
        str(other),
    )
    _git(other, "config", "user.email", "test@example.com")
    _git(other, "config", "user.name", "Test User")
    _git(other, "checkout", "-b", "feature/fetch-me", "origin/main")
    (other / "fetch.txt").write_text("fetch\n", encoding="utf-8")
    _git(other, "add", "fetch.txt")
    _git(other, "commit", "-m", "fetch branch")
    _git(other, "push", "-u", "origin", "feature/fetch-me")
    monkeypatch.setattr(
        GitBranchFetchCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )
    monkeypatch.setattr(
        GitBranchFetchCommand,
        "_get_raw_config",
        staticmethod(_remote_config),
    )
    monkeypatch.setattr(
        "code_analysis.commands.git_branch_fetch_pull_commands.build_full_subprocess_env",
        lambda _config: (None, None),
    )

    result = await GitBranchFetchCommand().execute(
        project_id=PROJECT_ID,
        branch="feature/fetch-me",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    branches = _git(
        repo_with_remote, "branch", "-r", "--list", "origin/feature/fetch-me"
    )
    assert "origin/feature/fetch-me" in branches


@pytest.mark.asyncio
async def test_git_branch_pull_fast_forwards_branch(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify branch pull fast-forwards the current branch."""
    other = repo_with_remote.parent / "other-pull"
    _git(
        repo_with_remote.parent,
        "clone",
        str(repo_with_remote.parent / "remote.git"),
        str(other),
    )
    _git(other, "config", "user.email", "test@example.com")
    _git(other, "config", "user.name", "Test User")
    (other / "pull.txt").write_text("pull\n", encoding="utf-8")
    _git(other, "add", "pull.txt")
    _git(other, "commit", "-m", "pull update")
    _git(other, "push", "origin", "main")
    monkeypatch.setattr(
        GitBranchPullCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )
    monkeypatch.setattr(
        GitBranchPullCommand,
        "_get_raw_config",
        staticmethod(_remote_config),
    )
    monkeypatch.setattr(
        "code_analysis.commands.git_branch_fetch_pull_commands.build_full_subprocess_env",
        lambda _config: (None, None),
    )

    result = await GitBranchPullCommand().execute(
        project_id=PROJECT_ID,
        branch="main",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert (repo_with_remote / "pull.txt").read_text(encoding="utf-8") == "pull\n"


@pytest.mark.asyncio
async def test_git_branch_compare_reports_ahead_and_files(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify branch compare reports commits and changed files."""
    monkeypatch.setattr(
        GitBranchCompareCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    result = await GitBranchCompareCommand().execute(
        project_id=PROJECT_ID,
        base="main",
        head="feature/local",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["ahead"] == 1
    assert result.data["behind"] == 0
    assert result.data["commits"][0]["message"] == "feature"
    assert result.data["files"][0]["path"] == "feature.txt"


@pytest.mark.asyncio
async def test_git_branch_sync_status_reports_tracking(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify sync status reports upstream states."""
    monkeypatch.setattr(
        GitBranchSyncStatusCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    result = await GitBranchSyncStatusCommand().execute(project_id=PROJECT_ID)

    assert isinstance(result, SuccessResult)
    by_name = {branch["name"]: branch for branch in result.data["branches"]}
    assert by_name["main"]["upstream"] == "origin/main"
    assert by_name["main"]["state"] == "up_to_date"
    assert by_name["feature/local"]["upstream"] == "origin/feature/local"


@pytest.mark.asyncio
async def test_git_branch_track_remote_creates_tracking_branch(
    repo_with_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify track remote creates a local branch with upstream."""
    _git(repo_with_remote, "branch", "-D", "feature/local")
    monkeypatch.setattr(
        GitBranchTrackRemoteCommand,
        "_resolve_project_root",
        lambda _self, _project_id: repo_with_remote,
    )

    result = await GitBranchTrackRemoteCommand().execute(
        project_id=PROJECT_ID,
        remote_branch="origin/feature/local",
        local_branch="feature/local",
        checkout=False,
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    branches = _git(repo_with_remote, "branch", "--list", "feature/local")
    assert "feature/local" in branches
    upstream = _git(
        repo_with_remote,
        "rev-parse",
        "--abbrev-ref",
        "feature/local@{upstream}",
    ).strip()
    assert upstream == "origin/feature/local"
