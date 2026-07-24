"""
Unit tests for EmergencyUnlockProjectMCPCommand (bugs 88f06abc, 5da73265).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.project_management_mcp_commands.emergency_unlock_project import (
    EmergencyUnlockProjectMCPCommand,
)

_PID = "550e8400-e29b-41d4-a716-446655440000"


def _fake_db() -> MagicMock:
    """Return a MagicMock db whose .select('projects', ...) yields one row."""
    db = MagicMock()
    db.select.return_value = [
        {
            "id": _PID,
            "root_path": "some_project",
            "name": "some_project",
            "watch_dir_id": "wd-1",
        }
    ]
    return db


async def _run_execute(**kwargs: object):
    """Run EmergencyUnlockProjectMCPCommand().execute() with the given kwargs."""
    return await EmergencyUnlockProjectMCPCommand().execute(**kwargs)  # type: ignore[arg-type]


class TestForceFalseIsReportOnly:
    """force=false never mutates the lock table."""

    @pytest.mark.asyncio
    async def test_force_false_never_releases_or_audits(self) -> None:
        """release_project_exclusive_lock / emergency_unlock_project_lock are never called."""
        db = _fake_db()
        with (
            patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db),
            patch(
                "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
                return_value={
                    "project_id": _PID,
                    "locked_at": 1.0,
                    "owner": "rename_project:abc",
                    "reason": "renaming",
                },
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.release_project_exclusive_lock"
            ) as mock_release,
            patch(
                "code_analysis.core.project_exclusive_lock.emergency_unlock_project_lock"
            ) as mock_audit,
            patch(
                "code_analysis.core.project_root_path.resolve_project_root_absolute_str",
                return_value="/watch/root/some_project",
            ),
        ):
            result = await _run_execute(project_id=_PID, force=False, reason="just checking")

        assert isinstance(result, SuccessResult)
        assert result.data["locked"] is True
        assert result.data["cleared"] is False
        mock_release.assert_not_called()
        mock_audit.assert_not_called()


class TestForceTrueClearsAndReportsMismatch:
    """force=true clears the lock and the response includes the mismatch dict."""

    @pytest.mark.asyncio
    async def test_force_true_calls_emergency_unlock_and_includes_mismatch(self) -> None:
        """emergency_unlock_project_lock is called once; response carries mismatch."""
        db = _fake_db()
        audit_record = {
            "project_id": _PID,
            "cleared": True,
            "force": True,
            "reason": "stuck rename",
            "mismatch": None,
            "previous_lock": {"owner": "rename_project:abc"},
            "at": 12345.0,
        }
        with (
            patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db),
            patch(
                "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
                return_value={
                    "project_id": _PID,
                    "locked_at": 1.0,
                    "owner": "rename_project:abc",
                    "reason": "renaming",
                },
            ),
            patch(
                "code_analysis.core.project_exclusive_lock.emergency_unlock_project_lock",
                return_value=audit_record,
            ) as mock_audit,
            patch(
                "code_analysis.core.project_root_path.resolve_project_root_absolute_str",
                return_value="/watch/root/some_project",
            ),
        ):
            result = await _run_execute(
                project_id=_PID, force=True, reason="stuck rename"
            )

        assert isinstance(result, SuccessResult)
        assert result.data["cleared"] is True
        assert result.data["audit"] == audit_record
        assert "mismatch" in result.data
        assert result.data["mismatch"]["stored_name"] == "some_project"
        mock_audit.assert_called_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["force"] is True
        assert kwargs["reason"] == "stuck rename"
