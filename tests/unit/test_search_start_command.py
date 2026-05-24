"""Unit tests for search_start paginated routing."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.search_start_command import SearchStartCommand
from code_analysis.core.search_session.directory import resolve_search_sessions_root
from code_analysis.core.search_session.result_index import COMPLETENESS_FINISHED
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

_VALID_PROJECT_ID = str(uuid.uuid4())


@dataclass
class _StoragePathsStub:
    config_dir: Path


def _mock_project_db() -> MagicMock:
    mock_db = MagicMock()
    mock_db.get_project.return_value = {"id": _VALID_PROJECT_ID}
    return mock_db


def _grep_matches() -> list[dict[str, object]]:
    return [
        {
            "relative_path": "src/app.py",
            "line_number": 10,
            "line": "needle here",
        }
    ]


def _fulltext_results() -> list[dict[str, object]]:
    return [
        {
            "chunk_uuid": "abc123",
            "chunk_type": "function",
            "name": "needle_fn",
            "relative_path": "src/app.py",
        }
    ]


def _semantic_results() -> list[dict[str, object]]:
    return [
        {
            "score": 0.85,
            "distance": 0.176,
            "chunk_uuid": "def456",
            "chunk_type": "method",
            "name": "needle_method",
            "relative_path": "src/service.py",
        }
    ]


@pytest.mark.asyncio
async def test_paginated_grep_creates_index_block_and_handoff(tmp_path: Path) -> None:
    cmd = SearchStartCommand()
    storage = _StoragePathsStub(config_dir=tmp_path)
    grep_result = SuccessResult(
        data={
            "success": True,
            "matches": _grep_matches(),
            "match_count": 1,
        }
    )

    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_mock_project_db(),
        ),
        patch.object(
            SearchStartCommand,
            "_get_shared_storage",
            return_value=storage,
        ),
        patch.object(
            SearchStartCommand,
            "_get_raw_config",
            return_value={"code_analysis": {"search_session": {}}},
        ),
        patch(
            "code_analysis.commands.search_start_command.FsGrepCommand.execute",
            new=AsyncMock(return_value=grep_result),
        ),
    ):
        result = await cmd.execute(
            project_id=_VALID_PROJECT_ID,
            search_type="grep",
            query="needle",
            paginated=True,
        )

    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["success"] is True
    assert data["paginated"] is True
    assert data["first_block_position"] == 1
    job_id = data["job_id"]
    assert job_id
    assert data["index_url"] == f"/search/jobs/{job_id}/index"

    session_root = resolve_search_sessions_root(tmp_path) / job_id
    assert session_root.is_dir()
    index_payload = json.loads(
        (session_root / "index.json").read_text(encoding="utf-8")
    )
    assert len(index_payload["blocks"]) == 1
    assert index_payload["blocks"][0]["position"] == 1
    assert index_payload["blocks"][0]["size_bytes"] > 0
    assert index_payload["completeness"] == COMPLETENESS_FINISHED
    assert (session_root / "blocks" / "block_1.json").is_file()


@pytest.mark.asyncio
async def test_paginated_fulltext_creates_index_block_and_handoff(
    tmp_path: Path,
) -> None:
    cmd = SearchStartCommand()
    storage = _StoragePathsStub(config_dir=tmp_path)
    fulltext_result = SuccessResult(
        data={
            "success": True,
            "results": _fulltext_results(),
            "count": 1,
        }
    )

    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_mock_project_db(),
        ),
        patch.object(
            SearchStartCommand,
            "_get_shared_storage",
            return_value=storage,
        ),
        patch.object(
            SearchStartCommand,
            "_get_raw_config",
            return_value={"code_analysis": {"search_session": {}}},
        ),
        patch(
            "code_analysis.commands.search_start_command.FulltextSearchMCPCommand.execute",
            new=AsyncMock(return_value=fulltext_result),
        ),
    ):
        result = await cmd.execute(
            project_id=_VALID_PROJECT_ID,
            search_type="fulltext",
            query="needle",
            paginated=True,
        )

    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["success"] is True
    assert data["paginated"] is True
    assert data["first_block_position"] == 1
    job_id = data["job_id"]
    assert job_id
    assert data["index_url"] == f"/search/jobs/{job_id}/index"

    session_root = resolve_search_sessions_root(tmp_path) / job_id
    assert session_root.is_dir()
    index_payload = json.loads(
        (session_root / "index.json").read_text(encoding="utf-8")
    )
    assert len(index_payload["blocks"]) == 1
    assert index_payload["blocks"][0]["position"] == 1
    assert index_payload["blocks"][0]["size_bytes"] > 0
    assert index_payload["completeness"] == COMPLETENESS_FINISHED
    assert (session_root / "blocks" / "block_1.json").is_file()


@pytest.mark.asyncio
async def test_paginated_semantic_creates_index_block_and_handoff(
    tmp_path: Path,
) -> None:
    cmd = SearchStartCommand()
    storage = _StoragePathsStub(config_dir=tmp_path)
    semantic_result = SuccessResult(
        data={
            "success": True,
            "results": _semantic_results(),
            "count": 1,
        }
    )

    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_mock_project_db(),
        ),
        patch.object(
            SearchStartCommand,
            "_get_shared_storage",
            return_value=storage,
        ),
        patch.object(
            SearchStartCommand,
            "_get_raw_config",
            return_value={"code_analysis": {"search_session": {}}},
        ),
        patch(
            "code_analysis.commands.search_start_command.SemanticSearchMCPCommand.execute",
            new=AsyncMock(return_value=semantic_result),
        ),
    ):
        result = await cmd.execute(
            project_id=_VALID_PROJECT_ID,
            search_type="semantic",
            query="needle",
            paginated=True,
        )

    assert isinstance(result, SuccessResult)
    data = result.data
    assert data["success"] is True
    assert data["paginated"] is True
    assert data["first_block_position"] == 1
    job_id = data["job_id"]
    assert job_id
    assert data["index_url"] == f"/search/jobs/{job_id}/index"

    session_root = resolve_search_sessions_root(tmp_path) / job_id
    assert session_root.is_dir()
    index_payload = json.loads(
        (session_root / "index.json").read_text(encoding="utf-8")
    )
    assert len(index_payload["blocks"]) == 1
    assert index_payload["blocks"][0]["position"] == 1
    assert index_payload["blocks"][0]["size_bytes"] > 0
    assert index_payload["completeness"] == COMPLETENESS_FINISHED
    assert (session_root / "blocks" / "block_1.json").is_file()


@pytest.mark.asyncio
async def test_paginated_grep_uses_maybe_route_paginated(tmp_path: Path) -> None:
    cmd = SearchStartCommand()
    storage = _StoragePathsStub(config_dir=tmp_path)
    grep_result = SuccessResult(
        data={
            "success": True,
            "matches": _grep_matches(),
            "match_count": 1,
        }
    )
    handoff_payload = {
        "success": True,
        "paginated": True,
        "job_id": "routed-job",
        "index_url": "/search/jobs/routed-job/index",
        "first_block_position": 1,
        "legacy_payload": None,
    }

    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_mock_project_db(),
        ),
        patch.object(
            SearchStartCommand,
            "_get_shared_storage",
            return_value=storage,
        ),
        patch.object(
            SearchStartCommand,
            "_get_raw_config",
            return_value={"code_analysis": {"search_session": {}}},
        ),
        patch(
            "code_analysis.commands.search_start_command.FsGrepCommand.execute",
            new=AsyncMock(return_value=grep_result),
        ),
        patch(
            "code_analysis.commands.search_start_command.maybe_route_paginated",
            return_value=handoff_payload,
        ) as route_mock,
    ):
        result = await cmd.execute(
            project_id=_VALID_PROJECT_ID,
            search_type="grep",
            query="needle",
            paginated=True,
        )

    assert isinstance(result, SuccessResult)
    assert result.data == handoff_payload
    route_mock.assert_called_once()
    call_kwargs = route_mock.call_args.kwargs
    assert call_kwargs["params"]["paginated"] is True
    assert call_kwargs["first_block_position"] == 1
    assert call_kwargs["session_factory"]().search_id
