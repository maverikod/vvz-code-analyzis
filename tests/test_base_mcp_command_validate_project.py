"""
Tests for BaseMCPCommand._validate_project_id_exists: transient RPC retry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.cst_save_tree_command import CSTSaveTreeCommand
from code_analysis.core.database_client.exceptions import (
    ConnectionError as DBConnectionError,
)
from code_analysis.core.exceptions import ValidationError

_VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


class TestValidateProjectIdExistsTransientRpc:
    """Connect-refused on get_project matches cst_save_tree retry policy."""

    def test_connect_refused_then_succeeds(self) -> None:
        """First two get_project calls raise connect-refused; third returns project."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        fake_project = MagicMock()
        mock_db.get_project.side_effect = [
            DBConnectionError("connection refused"),
            DBConnectionError("connection refused"),
            fake_project,
        ]
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch("code_analysis.commands.base_mcp_command.time.sleep"),
        ):
            BaseMCPCommand._validate_project_id_exists(_VALID_UUID)
        assert mock_db.get_project.call_count == 3

    def test_non_connect_refused_raises_immediately(self) -> None:
        """DBConnectionError without connect-refused is not retried."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        mock_db.get_project.side_effect = DBConnectionError("timeout")
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch("code_analysis.commands.base_mcp_command.time.sleep"),
        ):
            with pytest.raises(DBConnectionError):
                BaseMCPCommand._validate_project_id_exists(_VALID_UUID)
        assert mock_db.get_project.call_count == 1

    def test_missing_project_no_retry(self) -> None:
        """Missing project (None) raises ValidationError without retry."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        mock_db.get_project.return_value = None
        with patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=mock_db,
        ):
            with pytest.raises(ValidationError, match="not found"):
                BaseMCPCommand._validate_project_id_exists(_VALID_UUID)
        assert mock_db.get_project.call_count == 1


class TestCstSaveTreeValidateParamsUsesRetry:
    """validate_params delegates to _validate_project_id_exists."""

    def test_validate_params_succeeds_after_transient_failures(self) -> None:
        """Verify test validate params succeeds after transient failures."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        fake_project = MagicMock()
        mock_db.get_project.side_effect = [
            DBConnectionError("connection refused"),
            fake_project,
        ]
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch("code_analysis.commands.base_mcp_command.time.sleep"),
        ):
            params = CSTSaveTreeCommand().validate_params(
                {
                    "tree_id": "tid",
                    "project_id": _VALID_UUID,
                    "file_path": "x.py",
                }
            )
        assert params["project_id"] == _VALID_UUID
        assert mock_db.get_project.call_count == 2
