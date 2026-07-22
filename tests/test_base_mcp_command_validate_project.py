"""
Tests for BaseMCPCommand._validate_project_id_exists.

The retry-on-``DBConnectionError`` (connect-refused) wrapper was removed
(stage-2 driver-prep): ``core/database_client/factory.py`` confirms PostgreSQL
always runs in-process (no Unix socket, no driver subprocess), so a raw
connect-refused here can only mean the in-process RPC client is already
closed, not a transient network blip worth retrying. ``DBConnectionError`` now
propagates immediately.

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


class _ScopedMissGlobalHitDb:
    """Real ``get_project`` (scoped-select-miss -> global-by-id-hit fallback).

    Simulates an orphan project row registered under a different/rotated
    ``server_instance_id`` (e.g. after a server reinstall). Exercises the
    ACTUAL driver-direct ``domain.projects.get_project`` fallback logic (a
    duck-typed driver double implementing only ``select``/``execute``, not a
    mocked return value) - so this is a regression test for planner todo
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
    """DBConnectionError (any kind) propagates immediately; no retry."""

    def test_connect_refused_raises_immediately(self) -> None:
        """A connect-refused DBConnectionError propagates without retry."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.base_mcp_command.get_project",
                side_effect=DBConnectionError("connection refused"),
            ) as mock_get_project,
        ):
            with pytest.raises(DBConnectionError):
                BaseMCPCommand._validate_project_id_exists(_VALID_UUID)
        assert mock_get_project.call_count == 1
        mock_db.disconnect.assert_called_once()

    def test_non_connect_refused_raises_immediately(self) -> None:
        """DBConnectionError without connect-refused also propagates without retry."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.base_mcp_command.get_project",
                side_effect=DBConnectionError("timeout"),
            ) as mock_get_project,
        ):
            with pytest.raises(DBConnectionError):
                BaseMCPCommand._validate_project_id_exists(_VALID_UUID)
        assert mock_get_project.call_count == 1

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
                "code_analysis.core.database_driver_pkg.domain.projects."
                "current_server_instance_id",
                return_value="server-b-current",
            ),
            patch(
                "code_analysis.core.database_driver_pkg.domain.projects."
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
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.base_mcp_command.get_project",
                return_value=None,
            ) as mock_get_project,
        ):
            with pytest.raises(ValidationError, match="not found"):
                BaseMCPCommand._validate_project_id_exists(_VALID_UUID)
        assert mock_get_project.call_count == 1


class TestCstSaveTreeValidateParamsUsesRetry:
    """validate_params delegates to _validate_project_id_exists."""

    def test_validate_params_succeeds_when_project_exists(self) -> None:
        """validate_params returns params unchanged once the project is found."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.base_mcp_command.get_project",
                return_value=MagicMock(),
            ) as mock_get_project,
        ):
            params = CSTSaveTreeCommand().validate_params(
                {
                    "tree_id": "tid",
                    "project_id": _VALID_UUID,
                    "file_path": "x.py",
                }
            )
        assert params["project_id"] == _VALID_UUID
        assert mock_get_project.call_count == 1

    def test_validate_params_propagates_connection_error_immediately(self) -> None:
        """A DBConnectionError from get_project propagates without retry."""
        mock_db = MagicMock()
        mock_db.disconnect = MagicMock()
        with (
            patch.object(
                BaseMCPCommand,
                "_open_database_from_config",
                return_value=mock_db,
            ),
            patch(
                "code_analysis.commands.base_mcp_command.get_project",
                side_effect=DBConnectionError("connection refused"),
            ) as mock_get_project,
        ):
            with pytest.raises(DBConnectionError):
                CSTSaveTreeCommand().validate_params(
                    {
                        "tree_id": "tid",
                        "project_id": _VALID_UUID,
                        "file_path": "x.py",
                    }
                )
        assert mock_get_project.call_count == 1
