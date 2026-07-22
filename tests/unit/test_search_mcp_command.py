"""Unit tests for unified search MCP command."""

from __future__ import annotations

import threading
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.search_mcp_command import SearchMCPCommand
from code_analysis.core.exceptions import ValidationError
from mcp_proxy_adapter.commands.result import SuccessResult

_VALID_PROJECT_ID = str(uuid.uuid4())


def _mock_project_db() -> MagicMock:
    """Return mock project db."""
    mock_db = MagicMock()
    mock_db.get_project.return_value = {"id": _VALID_PROJECT_ID}
    return mock_db


@pytest.mark.asyncio
async def test_search_runs_background_in_dedicated_thread(tmp_path) -> None:
    """Verify test search runs background in dedicated thread."""
    cmd = SearchMCPCommand()
    sessions_root = tmp_path / "search_sessions"
    thread_started = threading.Event()

    def _capture_thread(**kwargs: object) -> None:
        """Return capture thread."""
        thread_started.set()
        layout = kwargs["layout"]
        (layout.blocks_dir / "block_1.json").write_text(
            '{"position": 1, "items": []}',
            encoding="utf-8",
        )

    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_mock_project_db(),
        ),
        patch(
            "code_analysis.commands.base_mcp_command.get_project",
            return_value={"id": _VALID_PROJECT_ID},
        ),
        patch.object(
            SearchMCPCommand,
            "_get_search_sessions_root",
            return_value=sessions_root,
        ),
        patch.object(
            SearchMCPCommand,
            "_get_raw_config",
            return_value={"search_session": {"max_block_size_bytes": 65536}},
        ),
        patch(
            "code_analysis.commands.search_mcp_command._run_paginated_cross_in_thread",
            side_effect=_capture_thread,
        ),
    ):
        result = await cmd.execute(
            project_id=_VALID_PROJECT_ID,
            query="needle",
            enable_semantic=False,
            enable_grep=False,
            first_block_wait_seconds=5,
        )

    assert isinstance(result, SuccessResult)
    assert thread_started.is_set()


@pytest.mark.asyncio
async def test_search_returns_handoff_with_job_id(tmp_path) -> None:
    """Verify test search returns handoff with job id."""
    cmd = SearchMCPCommand()
    sessions_root = tmp_path / "search_sessions"

    async def _fake_cross(**kwargs: object) -> int:
        """Return fake cross."""
        layout = kwargs["layout"]
        (layout.blocks_dir / "block_1.json").write_text(
            '{"position": 1, "items": [{"result_id": "ft-1", "source": "fulltext"}]}',
            encoding="utf-8",
        )
        return 1

    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_mock_project_db(),
        ),
        patch(
            "code_analysis.commands.base_mcp_command.get_project",
            return_value={"id": _VALID_PROJECT_ID},
        ),
        patch.object(
            SearchMCPCommand,
            "_get_search_sessions_root",
            return_value=sessions_root,
        ),
        patch.object(
            SearchMCPCommand,
            "_get_raw_config",
            return_value={"search_session": {"max_block_size_bytes": 65536}},
        ),
        patch(
            "code_analysis.commands.search_mcp_command.run_paginated_cross",
            new=AsyncMock(side_effect=_fake_cross),
        ),
    ):
        result = await cmd.execute(
            project_id=_VALID_PROJECT_ID,
            query="needle",
            enable_semantic=False,
            enable_grep=False,
            first_block_wait_seconds=5,
        )

    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["success"] is True
    assert data["paginated"] is True
    assert data["job_id"]
    assert data["index_url"] == f"/search/jobs/{data['job_id']}/index"
    assert data["first_block_position"] == 1
    assert data["block_position"] == 1
    assert data["ordering"] == "temporal"
    assert data["items"] == [{"result_id": "ft-1", "source": "fulltext"}]
    assert data["has_more"] in (True, False)
    assert (sessions_root / data["job_id"]).is_dir()


def test_search_accepts_path_filter_alias() -> None:
    """Verify test search accepts path filter alias."""
    cmd = SearchMCPCommand()
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_mock_project_db(),
        ),
        patch(
            "code_analysis.commands.base_mcp_command.get_project",
            return_value={"id": _VALID_PROJECT_ID},
        ),
    ):
        params = cmd.validate_params(
            {
                "project_id": _VALID_PROJECT_ID,
                "query": "needle",
                "path_filter": "code_analysis/commands",
            }
        )
    assert params["file_pattern"] == "code_analysis/commands"
    assert params["path_filter"] == "code_analysis/commands"


def test_search_rejects_conflicting_path_filter_and_file_pattern() -> None:
    """Verify test search rejects conflicting path filter and file pattern."""
    cmd = SearchMCPCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_project_db(),
    ):
        with pytest.raises(ValidationError):
            cmd.validate_params(
                {
                    "project_id": _VALID_PROJECT_ID,
                    "query": "needle",
                    "path_filter": "a",
                    "file_pattern": "b",
                }
            )
