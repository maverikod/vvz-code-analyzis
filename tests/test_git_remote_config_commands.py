"""Tests for git remote configuration MCP commands."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.git_remote_config_commands import (
    GitRemoteAddCommand,
    GitRemoteRemoveCommand,
    GitRemoteRenameCommand,
    GitRemoteSetPushUrlCommand,
    GitRemoteSetUrlCommand,
)

PROJECT_ID = "00000000-0000-0000-0000-000000000031"
REMOTE_CONFIG_COMMANDS = (
    GitRemoteAddCommand,
    GitRemoteSetUrlCommand,
    GitRemoteSetPushUrlCommand,
    GitRemoteRemoveCommand,
    GitRemoteRenameCommand,
)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


@pytest.fixture
def local_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("main\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    return repo


def _bind_project_root(
    command_cls: type, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        command_cls,
        "_resolve_project_root",
        lambda _self, _project_id: repo,
    )


def test_git_remote_config_schema_and_metadata_are_detailed() -> None:
    """Verify remote-config help contracts match the detailed git command style."""
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
    for command_cls in REMOTE_CONFIG_COMMANDS:
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
async def test_git_remote_add_adds_remote(
    local_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bind_project_root(GitRemoteAddCommand, local_repo, monkeypatch)

    result = await GitRemoteAddCommand().execute(
        project_id=PROJECT_ID,
        name="origin",
        url="git@github.com:owner/repo.git",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["operation"] == "add"
    assert _git(local_repo, "remote", "get-url", "origin").strip() == (
        "git@github.com:owner/repo.git"
    )


@pytest.mark.asyncio
async def test_git_remote_set_url_changes_remote_url(
    local_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(local_repo, "remote", "add", "origin", "git@github.com:owner/old.git")
    _bind_project_root(GitRemoteSetUrlCommand, local_repo, monkeypatch)

    result = await GitRemoteSetUrlCommand().execute(
        project_id=PROJECT_ID,
        name="origin",
        url="git@github.com:owner/new.git",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["operation"] == "set-url"
    assert _git(local_repo, "remote", "get-url", "origin").strip() == (
        "git@github.com:owner/new.git"
    )


@pytest.mark.asyncio
async def test_git_remote_set_push_url_changes_push_url(
    local_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(local_repo, "remote", "add", "origin", "git@github.com:owner/read.git")
    _bind_project_root(GitRemoteSetPushUrlCommand, local_repo, monkeypatch)

    result = await GitRemoteSetPushUrlCommand().execute(
        project_id=PROJECT_ID,
        name="origin",
        url="git@github.com:owner/write.git",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["operation"] == "set-push-url"
    assert _git(local_repo, "remote", "get-url", "--push", "origin").strip() == (
        "git@github.com:owner/write.git"
    )


@pytest.mark.asyncio
async def test_git_remote_rename_renames_remote(
    local_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(local_repo, "remote", "add", "origin", "git@github.com:owner/repo.git")
    _bind_project_root(GitRemoteRenameCommand, local_repo, monkeypatch)

    result = await GitRemoteRenameCommand().execute(
        project_id=PROJECT_ID,
        old_name="origin",
        new_name="upstream",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["operation"] == "rename"
    assert _git(local_repo, "remote").strip() == "upstream"


@pytest.mark.asyncio
async def test_git_remote_remove_removes_remote(
    local_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(local_repo, "remote", "add", "origin", "git@github.com:owner/repo.git")
    _bind_project_root(GitRemoteRemoveCommand, local_repo, monkeypatch)

    result = await GitRemoteRemoveCommand().execute(
        project_id=PROJECT_ID,
        name="origin",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["operation"] == "remove"
    assert _git(local_repo, "remote").strip() == ""


@pytest.mark.asyncio
async def test_git_remote_add_dry_run_does_not_mutate(
    local_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bind_project_root(GitRemoteAddCommand, local_repo, monkeypatch)

    result = await GitRemoteAddCommand().execute(
        project_id=PROJECT_ID,
        name="origin",
        url="git@github.com:owner/repo.git",
        dry_run=True,
    )

    assert isinstance(result, SuccessResult)
    assert result.data["dry_run"] is True
    assert result.data["would_run"] == [
        "git",
        "remote",
        "add",
        "origin",
        "git@github.com:owner/repo.git",
    ]
    assert _git(local_repo, "remote").strip() == ""


@pytest.mark.asyncio
async def test_git_remote_add_rejects_inline_http_credentials(
    local_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bind_project_root(GitRemoteAddCommand, local_repo, monkeypatch)

    result = await GitRemoteAddCommand().execute(
        project_id=PROJECT_ID,
        name="origin",
        url="https://user:secret@example.com/owner/repo.git",
    )

    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert result.details == {"field": "url"}
