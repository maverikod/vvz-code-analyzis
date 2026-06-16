"""Unit tests for unified search MCP command."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.search_mcp_command import SearchMCPCommand
from mcp_proxy_adapter.commands.result import SuccessResult

_VALID_PROJECT_ID = str(uuid.uuid4())


def _mock_project_db() -> MagicMock:
    mock_db = MagicMock()
    mock_db.get_project.return_value = {"id": _VALID_PROJECT_ID}
    return mock_db


@pytest.mark.asyncio
async def test_search_returns_handoff_with_job_id(tmp_path) -> None:
    cmd = SearchMCPCommand()
    sessions_root = tmp_path / "search_sessions"

    async def _fake_cross(**kwargs: object) -> int:
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
