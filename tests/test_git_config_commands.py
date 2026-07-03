"""
Tests for git config and identity MCP commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.git_worktree_commands import (
    GitConfigGetCommand,
    GitConfigListCommand,
    GitIdentityGetCommand,
    GitIdentitySetCommand,
)

PROJECT_ID = "00000000-0000-0000-0000-000000000041"
CONFIG_COMMANDS = (
    GitConfigGetCommand,
    GitConfigListCommand,
    GitIdentityGetCommand,
    GitIdentitySetCommand,
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
    """Create a small git repository without local identity."""
    _git(tmp_path, "init")
    return tmp_path


def test_git_config_command_schema_and_metadata_are_detailed() -> None:
    """Verify config command help contracts follow the metadata/schema standard."""
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
    for command_cls in CONFIG_COMMANDS:
        schema = command_cls.get_schema()
        metadata = command_cls.metadata()
        missing = required_metadata_keys - set(metadata)
        assert missing == set(), f"{command_cls.name} missing metadata keys: {missing}"
        assert schema["additionalProperties"] is False
        assert metadata["name"] == command_cls.name
        assert metadata["version"] == command_cls.version
        assert metadata["description"] == command_cls.descr
        assert len(metadata["detailed_description"]) > 400
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
async def test_git_config_get_reports_missing_local_key(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify missing keys are returned as configured=false."""
    _patch_root(GitConfigGetCommand, repo, monkeypatch)

    result = await GitConfigGetCommand().execute(
        project_id=PROJECT_ID,
        key="user.name",
    )

    assert isinstance(result, SuccessResult)
    assert result.data["success"] is True
    assert result.data["configured"] is False
    assert result.data["value"] is None


@pytest.mark.asyncio
async def test_git_identity_set_writes_local_identity_and_get_reads_it(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify identity_set writes local config and identity_get reads it."""
    _patch_root(GitIdentitySetCommand, repo, monkeypatch)
    _patch_root(GitIdentityGetCommand, repo, monkeypatch)
    _patch_root(GitConfigGetCommand, repo, monkeypatch)
    _patch_root(GitConfigListCommand, repo, monkeypatch)

    set_result = await GitIdentitySetCommand().execute(
        project_id=PROJECT_ID,
        name="casmgr-smoke",
        email="casmgr-smoke@localhost",
    )

    assert isinstance(set_result, SuccessResult)
    assert set_result.data["success"] is True
    assert set_result.data["scope"] == "local"
    assert set_result.data["current"]["configured"] is True
    assert (
        _git(repo, "config", "--local", "--get", "user.name").strip() == "casmgr-smoke"
    )
    assert (
        _git(repo, "config", "--local", "--get", "user.email").strip()
        == "casmgr-smoke@localhost"
    )

    identity_result = await GitIdentityGetCommand().execute(project_id=PROJECT_ID)
    assert isinstance(identity_result, SuccessResult)
    assert identity_result.data["configured"] is True
    assert identity_result.data["local"]["name"] == "casmgr-smoke"
    assert identity_result.data["effective"]["email"] == "casmgr-smoke@localhost"

    get_result = await GitConfigGetCommand().execute(
        project_id=PROJECT_ID,
        key="user.email",
    )
    assert isinstance(get_result, SuccessResult)
    assert get_result.data["configured"] is True
    assert get_result.data["value"] == "casmgr-smoke@localhost"

    list_result = await GitConfigListCommand().execute(
        project_id=PROJECT_ID,
        scope="local",
    )
    assert isinstance(list_result, SuccessResult)
    by_key = {entry["key"]: entry for entry in list_result.data["entries"]}
    assert by_key["user.name"]["value"] == "casmgr-smoke"
    assert "origin" in by_key["user.name"]


@pytest.mark.asyncio
async def test_git_identity_set_rejects_global_without_explicit_allow(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify global identity writes require allow_global=true."""
    _patch_root(GitIdentitySetCommand, repo, monkeypatch)

    result = await GitIdentitySetCommand().execute(
        project_id=PROJECT_ID,
        name="casmgr-smoke",
        email="casmgr-smoke@localhost",
        scope="global",
    )

    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert result.details == {"field": "allow_global"}
