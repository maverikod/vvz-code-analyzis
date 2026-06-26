"""
Tests for RunUuidIdentityMigrationMCPCommand (registration and execute safety).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.file_management_mcp_commands.run_uuid_identity_migration import (
    RunUuidIdentityMigrationMCPCommand,
)
from code_analysis.core.database.migrations.uuid_identity_postgres_data_migrate import (
    Phase345Report,
)
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


@dataclass
class _FakePreflight:
    """Represent FakePreflight."""

    backend: str = "sqlite"
    projects_uuid_ok: bool = True
    watch_dirs_uuid_ok: bool = True
    notes: List[str] = None
    warnings: List[str] = None

    def __post_init__(self) -> None:
        """Return post init."""
        if self.notes is None:
            self.notes = []
        if self.warnings is None:
            self.warnings = []


@dataclass
class _FakePhase2:
    """Represent FakePhase2."""

    backend: str = "sqlite"
    migration_tables: Tuple[str, ...] = ("uuid_migration_files",)
    counts: Dict[str, Tuple[int, int]] = None

    def __post_init__(self) -> None:
        """Return post init."""
        if self.counts is None:
            self.counts = {"uuid_migration_files": (0, 0)}


def test_command_name_and_schema() -> None:
    """Verify test command name and schema."""
    assert RunUuidIdentityMigrationMCPCommand.name == "run_uuid_identity_migration"
    schema = RunUuidIdentityMigrationMCPCommand.get_schema()
    assert "action" in schema["properties"]
    assert "preflight" in schema["properties"]["action"]["enum"]


def _fake_queue_context() -> Dict[str, Any]:
    """Minimal context as passed by mcp_proxy_adapter CommandExecutionJob (queue worker)."""
    return {"progress_tracker": object()}


def test_registration_import_from_hooks_part2() -> None:
    """register_commands_part2 imports the new command class."""
    from code_analysis.hooks_register_part2 import register_commands_part2

    assert callable(register_commands_part2)
    from code_analysis.commands.file_management_mcp_commands import (
        RunUuidIdentityMigrationMCPCommand as _Cmd,
    )

    assert _Cmd is RunUuidIdentityMigrationMCPCommand


@pytest.mark.asyncio
async def test_phase6_swap_refuses_without_confirmation() -> None:
    """Verify test phase6 swap refuses without confirmation."""
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()
    with patch.object(
        RunUuidIdentityMigrationMCPCommand,
        "_open_database_from_config",
        return_value=mock_db,
    ):
        cmd = RunUuidIdentityMigrationMCPCommand()
        result = await cmd.execute(
            action="phase6_swap",
            i_confirm_maintenance_swap=False,
        )
    assert isinstance(result, ErrorResult)
    assert result.code == "UUID_MIGRATION_CONFIRMATION_REQUIRED"
    mock_db.disconnect.assert_not_called()


@pytest.mark.asyncio
async def test_preflight_success_mocked() -> None:
    """Verify test preflight success mocked."""
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()
    fake = _FakePreflight()

    with (
        patch.object(
            RunUuidIdentityMigrationMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch(
            "code_analysis.commands.file_management_mcp_commands."
            "run_uuid_identity_migration.run_uuid_migration_preflight_phase1",
            return_value=fake,
        ),
        patch(
            "code_analysis.commands.file_management_mcp_commands."
            "run_uuid_identity_migration.detect_backend_kind",
            return_value="sqlite",
        ),
    ):
        cmd = RunUuidIdentityMigrationMCPCommand()
        result = await cmd.execute(action="preflight", context=_fake_queue_context())

    assert isinstance(result, SuccessResult)
    assert result.data["backend"] == "sqlite"
    assert result.data["steps"][0]["step"] == "preflight_phase1"
    mock_db.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_dry_does_not_call_phase6() -> None:
    """Verify test pipeline dry does not call phase6."""
    mock_db = MagicMock()
    mock_db.disconnect = MagicMock()
    fake_pre = _FakePreflight()
    fake2 = _FakePhase2()
    rep345 = Phase345Report(
        backend="sqlite",
        shadow_prefix="uuid_mig_new_",
        dry_run=True,
        statements_executed=0,
        row_counts_source_vs_shadow={},
        validation={},
        sql_log=["SELECT 1"],
    )
    swap_pg = MagicMock()
    swap_sl = MagicMock()

    with (
        patch.object(
            RunUuidIdentityMigrationMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ),
        patch(
            "code_analysis.commands.file_management_mcp_commands."
            "run_uuid_identity_migration.run_uuid_migration_preflight_phase1",
            return_value=fake_pre,
        ),
        patch(
            "code_analysis.commands.file_management_mcp_commands."
            "run_uuid_identity_migration.run_uuid_migration_phase2_build_mappings",
            return_value=fake2,
        ),
        patch(
            "code_analysis.commands.file_management_mcp_commands."
            "run_uuid_identity_migration.run_uuid_migration_phases_3_to_5_sqlite",
            return_value=rep345,
        ),
        patch(
            "code_analysis.commands.file_management_mcp_commands."
            "run_uuid_identity_migration.run_uuid_migration_phase6_swap_sqlite",
            swap_sl,
        ),
        patch(
            "code_analysis.commands.file_management_mcp_commands."
            "run_uuid_identity_migration.run_uuid_migration_phase6_swap_postgres",
            swap_pg,
        ),
        patch(
            "code_analysis.commands.file_management_mcp_commands."
            "run_uuid_identity_migration.detect_backend_kind",
            return_value="sqlite",
        ),
    ):
        cmd = RunUuidIdentityMigrationMCPCommand()
        result = await cmd.execute(action="pipeline_dry", context=_fake_queue_context())

    assert isinstance(result, SuccessResult)
    assert len(result.data["steps"]) == 3
    swap_sl.assert_not_called()
    swap_pg.assert_not_called()


def test_schema_creation_reexports() -> None:
    """Verify test schema creation reexports."""
    from code_analysis.core.database import schema_creation as sc

    assert callable(sc.run_uuid_migration_preflight_phase1)
    assert callable(sc.run_uuid_migration_phases_3_to_5_sqlite)
    assert callable(sc.run_uuid_migration_phase6_swap_sqlite)


def test_run_uuid_identity_migration_is_queued_by_default() -> None:
    """Verify test run uuid identity migration is queued by default."""
    assert RunUuidIdentityMigrationMCPCommand.use_queue is True


@pytest.mark.asyncio
async def test_preflight_rejects_without_queue_context() -> None:
    """Verify test preflight rejects without queue context."""
    cmd = RunUuidIdentityMigrationMCPCommand()
    result = await cmd.execute(action="preflight")
    assert isinstance(result, ErrorResult)
    assert result.code == "UUID_MIGRATION_QUEUE_REQUIRED"
