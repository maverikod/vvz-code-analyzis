"""
Targeted tests for cst_save_tree command: transient connect refusal recovery,
transient DB lock recovery, retry budget exhaustion, non-transient fast-fail.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.cst_save_tree_command import CSTSaveTreeCommand
from code_analysis.core.database_client.exceptions import (
    ConnectionError as DBConnectionError,
)


def _success_result(file_path: str) -> dict:
    """Minimal success dict from save_tree_to_file."""
    return {
        "success": True,
        "file_path": file_path,
        "file_id": 1,
        "update_result": {"success": True},
    }


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Temporary project root."""
    return tmp_path


@pytest.fixture
def out_py(project_root: Path) -> Path:
    """Target file path; file created so command can read size/lines after save."""
    p = project_root / "out.py"
    p.write_text("x = 1\n", encoding="utf-8")
    return p


class TestCstSaveTreeTransientConnectRefusalRecovery:
    """Transient connect refusal then recovery: retry until success."""

    @pytest.mark.asyncio
    async def test_connect_refused_then_success(
        self, project_root: Path, out_py: Path
    ) -> None:
        """First 2 attempts raise connection refused, 3rd succeeds."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        call_count = 0

        def open_db(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise DBConnectionError("connection refused")
            return mock_db

        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            side_effect=open_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=out_py,
        ), patch(
            "code_analysis.commands.cst_save_tree_command.save_tree_to_file"
        ) as mock_save:
            mock_save.return_value = _success_result(str(out_py))
            with patch(
                "code_analysis.commands.cst_save_tree_command.reload_tree_from_file"
            ), patch(
                "code_analysis.commands.cst_save_tree_command.commit_after_write",
                return_value=(True, None),
            ):
                cmd = CSTSaveTreeCommand()
                result = await cmd.execute(
                    tree_id="test-tree-id",
                    project_id="test-project-id",
                    file_path="out.py",
                )
        assert isinstance(result, SuccessResult)
        assert result.data.get("success") is True
        assert call_count == 3


class TestCstSaveTreeTransientConnectRefusedInSaveResult:
    """Connect refused surfaced as save_tree_to_file error string (not raised DBConnectionError)."""

    @pytest.mark.asyncio
    async def test_connect_refused_in_save_result_then_success(
        self, project_root: Path, out_py: Path
    ) -> None:
        """First 2 save results report connection refused in error text, 3rd succeeds."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        refused = {
            "success": False,
            "error": "Failed to sync file to DB: [Errno 111] Connection refused",
            "file_path": str(out_py),
        }
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=out_py,
        ), patch(
            "code_analysis.commands.cst_save_tree_command.save_tree_to_file"
        ) as mock_save:
            mock_save.side_effect = [refused, refused, _success_result(str(out_py))]
            with patch(
                "code_analysis.commands.cst_save_tree_command.reload_tree_from_file"
            ), patch(
                "code_analysis.commands.cst_save_tree_command.commit_after_write",
                return_value=(True, None),
            ):
                cmd = CSTSaveTreeCommand()
                result = await cmd.execute(
                    tree_id="test-tree-id",
                    project_id="test-project-id",
                    file_path="out.py",
                )
        assert isinstance(result, SuccessResult)
        assert result.data.get("success") is True
        assert mock_save.call_count == 3


class TestCstSaveTreeTransientDbLockRecovery:
    """Transient DB lock then success: retry until save succeeds."""

    @pytest.mark.asyncio
    async def test_db_locked_then_success(
        self, project_root: Path, out_py: Path
    ) -> None:
        """First 2 save results are 'database is locked', 3rd succeeds."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        save_call_count = 0

        async def save_mock(*args, **kwargs):
            nonlocal save_call_count
            save_call_count += 1
            if save_call_count <= 2:
                return {
                    "success": False,
                    "error": "database is locked",
                    "file_path": str(out_py),
                }
            return _success_result(str(out_py))

        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=out_py,
        ), patch(
            "code_analysis.commands.cst_save_tree_command.save_tree_to_file"
        ) as mock_save:

            def sync_save(*args, **kwargs):
                import asyncio

                return asyncio.get_event_loop().run_until_complete(
                    save_mock(*args, **kwargs)
                )

            # run_until_complete from inside async test is problematic; use side_effect list instead
            mock_save.side_effect = [
                {
                    "success": False,
                    "error": "database is locked",
                    "file_path": str(out_py),
                },
                {
                    "success": False,
                    "error": "database is locked",
                    "file_path": str(out_py),
                },
                _success_result(str(out_py)),
            ]
            with patch(
                "code_analysis.commands.cst_save_tree_command.reload_tree_from_file"
            ), patch(
                "code_analysis.commands.cst_save_tree_command.commit_after_write",
                return_value=(True, None),
            ):
                cmd = CSTSaveTreeCommand()
                result = await cmd.execute(
                    tree_id="test-tree-id",
                    project_id="test-project-id",
                    file_path="out.py",
                )
        assert isinstance(result, SuccessResult)
        assert result.data.get("success") is True
        assert mock_save.call_count == 3


class TestCstSaveTreeRetryBudgetExhaustion:
    """Retry budget exhaustion: fail with clear message after max attempts."""

    @pytest.mark.asyncio
    async def test_connect_refused_exhaustion(
        self, project_root: Path, out_py: Path
    ) -> None:
        """All 4 attempts raise connection refused; return ErrorResult with suffix."""
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            side_effect=DBConnectionError("connection refused"),
        ):
            cmd = CSTSaveTreeCommand()
            result = await cmd.execute(
                tree_id="test-tree-id",
                project_id="test-project-id",
                file_path="out.py",
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_SAVE_ERROR"
        assert "after 4 attempts" in result.message
        assert "s total" in result.message

    @pytest.mark.asyncio
    async def test_db_locked_exhaustion(self, project_root: Path, out_py: Path) -> None:
        """All attempts return database is locked; return ErrorResult with suffix."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        lock_result = {
            "success": False,
            "error": "database is locked",
            "file_path": str(out_py),
        }
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=out_py,
        ), patch(
            "code_analysis.commands.cst_save_tree_command.save_tree_to_file",
            return_value=lock_result,
        ):
            cmd = CSTSaveTreeCommand()
            result = await cmd.execute(
                tree_id="test-tree-id",
                project_id="test-project-id",
                file_path="out.py",
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_SAVE_ERROR"
        assert "database is locked" in result.message
        assert "after 4 attempts" in result.message

    @pytest.mark.asyncio
    async def test_connect_refused_in_save_result_exhaustion(
        self, project_root: Path, out_py: Path
    ) -> None:
        """All attempts return connect-refused in save error text; fail with suffix."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        refused = {
            "success": False,
            "error": "Failed to sync file to DB: connection refused",
            "file_path": str(out_py),
        }
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=out_py,
        ), patch(
            "code_analysis.commands.cst_save_tree_command.save_tree_to_file",
            return_value=refused,
        ):
            cmd = CSTSaveTreeCommand()
            result = await cmd.execute(
                tree_id="test-tree-id",
                project_id="test-project-id",
                file_path="out.py",
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_SAVE_ERROR"
        assert "connection refused" in result.message.lower()
        assert "after 4 attempts" in result.message


class TestCstSaveTreeNonTransientFastFail:
    """Non-transient errors: no retry, immediate ErrorResult."""

    @pytest.mark.asyncio
    async def test_connection_error_not_refused_raises_no_retry(
        self, project_root: Path, out_py: Path
    ) -> None:
        """ConnectionError without connect-refused is not retried (propagates)."""
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            side_effect=DBConnectionError("timeout"),
        ):
            cmd = CSTSaveTreeCommand()
            result = await cmd.execute(
                tree_id="test-tree-id",
                project_id="test-project-id",
                file_path="out.py",
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_SAVE_ERROR"
        assert "timeout" in result.message
        assert "after 4 attempts" not in result.message

    @pytest.mark.asyncio
    async def test_save_non_lock_error_no_retry(
        self, project_root: Path, out_py: Path
    ) -> None:
        """Save result with non-lock error returns immediately (no retry)."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ), patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=out_py,
        ), patch(
            "code_analysis.commands.cst_save_tree_command.save_tree_to_file",
            return_value={
                "success": False,
                "error": "FOREIGN KEY constraint failed",
                "file_path": str(out_py),
            },
        ):
            cmd = CSTSaveTreeCommand()
            result = await cmd.execute(
                tree_id="test-tree-id",
                project_id="test-project-id",
                file_path="out.py",
            )
        assert isinstance(result, ErrorResult)
        assert result.code == "CST_SAVE_ERROR"
        assert "FOREIGN KEY" in result.message
        assert "after 4 attempts" not in result.message
