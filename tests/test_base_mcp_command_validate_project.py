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
from code_analysis.core.database_client.client_api_projects import (
    _ClientAPIProjectsMixin,
)
from code_analysis.core.database_client.exceptions import (
    ConnectionError as DBConnectionError,
)
from code_analysis.core.exceptions import ValidationError

_VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


class _ScopedMissGlobalHitDb(_ClientAPIProjectsMixin):
    """Real ``get_project`` (scoped-select-miss -> global-by-id-hit fallback).

    Simulates an orphan project row registered under a different/rotated
    ``server_instance_id`` (e.g. after a server reinstall). Exercises the
    ACTUAL ``_ClientAPIProjectsMixin.get_project`` fallback logic - not a
    mocked return value - so this is a regression test for planner todo
    b235f6da: ``BaseMCPCommand._validate_project_id_exists`` must not reject
    a project_id that ``_resolve_project_root`` (unscoped) can see.
    """

    def __init__(self) -> None:
        """Initialize the instance."""
        self.rpc_client = MagicMock()

    def disconnect(self) -> None:
        """No-op disconnect for the RPC-less test double."""

    def select(self, table_name, where=None, **_kwargs):  # type: ignore[no-untyped-def]
        """Scoped select always misses (row lives under a different sid)."""
        return []

    def execute(self, sql, params=None, transaction_id=None, *, priority=0):  # type: ignore[no-untyped-def]
        """Global-by-id lookup hits a row registered under a different sid."""
        if "FROM projects WHERE id =" in sql:
            return {
                "data": [
                    {
                        "id": _VALID_UUID,
                        "server_instance_id": "server-a-orphan",
                        "root_path": "orphan_proj",
                        "name": "orphan_proj",
                        "comment": None,
                        "watch_dir_id": None,
                    }
                ]
            }
        return {"data": []}


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

    def test_scoped_miss_global_hit_via_real_get_project_fallback(self) -> None:
        """Orphan project (scoped select misses, global-by-id hits) still validates."""
        db = _ScopedMissGlobalHitDb()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=db,
            ),
            patch(
                "code_analysis.core.database_client.client_api_projects."
                "current_server_instance_id",
                return_value="server-b-current",
            ),
            patch(
                "code_analysis.core.database_client.client_api_projects."
                "enrich_project_dict_resolve_root_path",
                side_effect=lambda row, _db: dict(row),
            ),
        ):
            # No exception -> validated successfully via the global-by-id fallback.
            BaseMCPCommand._validate_project_id_exists(_VALID_UUID)

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
