"""
Unit tests for RenameProjectMCPCommand (bugs 88f06abc, 5da73265).

Args ``db``/``self._resolve_project_root``/the domain relocate function are all
mocked - no real filesystem or PostgreSQL is required.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.project_management_mcp_commands.rename_project import (
    RenameProjectMCPCommand,
)

_PID = "550e8400-e29b-41d4-a716-446655440000"


def _fake_db(root_path: str = "some_project") -> MagicMock:
    """Return a MagicMock db whose .select('projects', ...) yields one row."""
    db = MagicMock()
    db.select.return_value = [
        {
            "id": _PID,
            "root_path": root_path,
            "name": "some_project",
            "watch_dir_id": "wd-1",
        }
    ]
    return db


async def _run_execute(**kwargs: object):
    """Run RenameProjectMCPCommand().execute() with the given kwargs."""
    return await RenameProjectMCPCommand().execute(**kwargs)  # type: ignore[arg-type]


class TestNewNameValidation:
    """Step 0: new_name validation happens before anything else."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_name", ["", "   ", "a/b", "a\\b", ".", ".."]
    )
    async def test_rejects_invalid_new_name(self, bad_name: str) -> None:
        """Each invalid new_name is rejected with VALIDATION_ERROR."""
        db = _fake_db()
        with (
            patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db),
            patch(
                "code_analysis.core.project_exclusive_lock.acquire_project_exclusive_lock"
            ) as mock_acquire,
        ):
            result = await _run_execute(project_id=_PID, new_name=bad_name)

        assert isinstance(result, ErrorResult)
        assert result.code == "VALIDATION_ERROR"
        mock_acquire.assert_not_called()


class TestLegacyProjectRejection:
    """Legacy absolute-path projects are rejected before any lock is taken."""

    @pytest.mark.asyncio
    async def test_legacy_storage_project_rejected_before_lock(self) -> None:
        """RENAME_LEGACY_PROJECT_NOT_SUPPORTED; acquire_project_exclusive_lock never called."""
        db = _fake_db(root_path="/absolute/legacy/path")
        with (
            patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db),
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=Path("/absolute/legacy/path"),
            ),
            patch(
                "code_analysis.core.project_root_path.is_legacy_projects_root_path_absolute_storage",
                return_value=True,
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.acquire_project_exclusive_lock"
            ) as mock_acquire,
        ):
            result = await _run_execute(project_id=_PID, new_name="new_name")

        assert isinstance(result, ErrorResult)
        assert result.code == "RENAME_LEGACY_PROJECT_NOT_SUPPORTED"
        mock_acquire.assert_not_called()


class TestLockAlreadyHeld:
    """Step 1: lock already held by someone else."""

    @pytest.mark.asyncio
    async def test_lock_already_held_returns_project_locked_no_rename(self) -> None:
        """PROJECT_LOCKED is returned and os.rename is never attempted."""
        db = _fake_db()
        with (
            patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db),
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=Path("/watch/root/some_project"),
            ),
            patch(
                "code_analysis.core.project_root_path.is_legacy_projects_root_path_absolute_storage",
                return_value=False,
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.acquire_project_exclusive_lock",
                return_value=False,
            ),
            patch(
                "code_analysis.commands.project_management_mcp_commands.rename_project.os.rename"
            ) as mock_rename,
        ):
            result = await _run_execute(project_id=_PID, new_name="new_name")

        assert isinstance(result, ErrorResult)
        assert result.code == "PROJECT_LOCKED"
        mock_rename.assert_not_called()


class TestOsRenameFailure:
    """Step 2: os.rename raises OSError -> lock stays held."""

    @pytest.mark.asyncio
    async def test_os_rename_failure_keeps_lock_held(self) -> None:
        """RENAME_OS_ERROR is returned and release_project_exclusive_lock is never called."""
        db = _fake_db()
        with (
            patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db),
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=Path("/watch/root/some_project"),
            ),
            patch(
                "code_analysis.core.project_root_path.is_legacy_projects_root_path_absolute_storage",
                return_value=False,
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.acquire_project_exclusive_lock",
                return_value=True,
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.release_project_exclusive_lock"
            ) as mock_release,
            patch(
                "code_analysis.commands.project_management_mcp_commands.rename_project.os.rename",
                side_effect=OSError("permission denied"),
            ),
        ):
            result = await _run_execute(project_id=_PID, new_name="new_name")

        assert isinstance(result, ErrorResult)
        assert result.code == "RENAME_OS_ERROR"
        mock_release.assert_not_called()


class TestDbUpdateFailure:
    """Step 3: relocate_project_root_after_disk_move returns False -> lock stays held."""

    @pytest.mark.asyncio
    async def test_db_update_failure_keeps_lock_held(self) -> None:
        """RENAME_DB_UPDATE_FAILED is returned; release_project_exclusive_lock never called."""
        db = _fake_db()
        with (
            patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db),
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=Path("/watch/root/some_project"),
            ),
            patch(
                "code_analysis.core.project_root_path.is_legacy_projects_root_path_absolute_storage",
                return_value=False,
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.acquire_project_exclusive_lock",
                return_value=True,
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.release_project_exclusive_lock"
            ) as mock_release,
            patch(
                "code_analysis.commands.project_management_mcp_commands.rename_project.os.rename"
            ),
            patch(
                "code_analysis.core.database_driver_pkg.domain.projects."
                "relocate_project_root_after_disk_move",
                return_value=False,
            ),
        ):
            result = await _run_execute(project_id=_PID, new_name="new_name")

        assert isinstance(result, ErrorResult)
        assert result.code == "RENAME_DB_UPDATE_FAILED"
        mock_release.assert_not_called()


class TestHappyPath:
    """Full success: lock acquired then released, SuccessResult with new name/root_path."""

    @pytest.mark.asyncio
    async def test_full_success_acquires_then_releases_lock(self) -> None:
        """acquire then release are each called exactly once, in that order."""
        db = _fake_db()
        call_order: list[str] = []

        def _acquire(*args: object, **kwargs: object) -> bool:
            call_order.append("acquire")
            return True

        def _release(*args: object, **kwargs: object) -> None:
            call_order.append("release")

        with (
            patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db),
            patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                return_value=Path("/watch/root/some_project"),
            ),
            patch(
                "code_analysis.core.project_root_path.is_legacy_projects_root_path_absolute_storage",
                return_value=False,
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.acquire_project_exclusive_lock",
                side_effect=_acquire,
            ) as mock_acquire,
            patch(
                "code_analysis.core.project_exclusive_lock.release_project_exclusive_lock",
                side_effect=_release,
            ) as mock_release,
            patch(
                "code_analysis.commands.project_management_mcp_commands.rename_project.os.rename"
            ) as mock_os_rename,
            patch(
                "code_analysis.core.database_driver_pkg.domain.projects."
                "relocate_project_root_after_disk_move",
                return_value=True,
            ),
        ):
            result = await _run_execute(project_id=_PID, new_name="renamed_project")

        assert isinstance(result, SuccessResult)
        assert result.data["project_id"] == _PID
        assert result.data["old_name"] == "some_project"
        assert result.data["new_name"] == "renamed_project"
        assert result.data["root_path"] == str(
            Path("/watch/root/some_project").parent / "renamed_project"
        )
        mock_acquire.assert_called_once()
        mock_release.assert_called_once()
        mock_os_rename.assert_called_once()
        assert call_order == ["acquire", "release"]
