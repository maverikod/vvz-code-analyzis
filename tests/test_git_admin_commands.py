"""Contract tests for git repository administration commands."""

from __future__ import annotations

from typing import Any, Dict, Type

from code_analysis.commands.git_admin_commands import (
    GitPullSafeCommand,
    GitRepoDoctorCommand,
    GitRepoLockCleanupCommand,
    GitRepoPermissionsCheckCommand,
    GitRepoPermissionsRepairCommand,
)

COMMANDS = [
    GitRepoPermissionsCheckCommand,
    GitRepoPermissionsRepairCommand,
    GitRepoDoctorCommand,
    GitRepoLockCleanupCommand,
    GitPullSafeCommand,
]


def _assert_schema(command: Type[Any]) -> None:
    schema = command.get_schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "project_id" in schema["required"]
    assert schema["properties"]["project_id"]["type"] == "string"
    assert schema["properties"]["project_id"]["description"]


def _assert_metadata(command: Type[Any]) -> None:
    metadata: Dict[str, Any] = command.metadata()
    assert metadata["name"] == command.get_name()
    assert metadata["description"]
    assert metadata["detailed_description"]
    assert metadata["parameters"]["project_id"]["description"]
    assert metadata["return_value"]["success"]["description"]
    assert metadata["return_value"]["error"]["description"]
    assert metadata["usage_examples"]
    assert metadata["error_cases"]
    assert metadata["best_practices"]


def test_git_admin_commands_publish_strict_schemas() -> None:
    for command in COMMANDS:
        _assert_schema(command)


def test_git_admin_commands_publish_man_page_metadata() -> None:
    for command in COMMANDS:
        _assert_metadata(command)
