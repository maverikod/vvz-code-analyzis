"""Tests for paginated semantic adapter (T-003/A-006)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from code_analysis.commands.search_paginated_semantic import (
    normalize_semantic_finding,
    run_paginated_semantic,
)
from code_analysis.core.search_session.session import SearchSession, SearchSessionState
from mcp_proxy_adapter.commands.result import SuccessResult


def _session_and_layout(tmp_path: Path):
    """Return session and layout."""
    from code_analysis.core.search_session.directory import (
        provision_search_session_directory,
    )

    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        sessions_root=tmp_path / "search_sessions", search_id=search_id
    )
    session = SearchSession(
        search_id=search_id,
        state=SearchSessionState.running,
        directory_path=layout.root,
    )
    return session, layout


def _fake_assembler_factory(layout, raw_config):
    """Return fake assembler factory."""
    assembler = MagicMock()

    def run(search_completed=False):
        """Return run."""
        (layout.blocks_dir / "block_1.json").write_text(
            json.dumps({"position": 1, "items": []})
        )

    assembler.run_until_idle.side_effect = run
    return assembler


def test_normalize_semantic_finding() -> None:
    """Verify test normalize semantic finding."""
    raw = {"file_path": "b.py", "score": 0.9, "chunk_text": "foo"}
    finding = normalize_semantic_finding(raw, index=0)
    assert finding["result_id"] == "semantic-000000"
    assert finding["source"] == "semantic"
    assert finding["file_path"] == "b.py"
    assert finding["preview"] is None


@pytest.mark.asyncio
async def test_run_paginated_semantic_returns_1_on_results(tmp_path: Path) -> None:
    """Verify test run paginated semantic returns 1 on results."""
    session, layout = _session_and_layout(tmp_path)
    command = MagicMock()
    command.execute = AsyncMock(
        return_value=SuccessResult(
            data={"results": [{"file_path": "b.py", "score": 0.9}]}
        )
    )
    pos = await run_paginated_semantic(
        command=command,
        params={"project_id": "pid", "query": "q"},
        session=session,
        layout=layout,
        raw_config={},
        block_assembler_factory=_fake_assembler_factory,
    )
    assert pos == 1


@pytest.mark.asyncio
async def test_run_paginated_semantic_returns_none_on_empty(tmp_path: Path) -> None:
    """Verify test run paginated semantic returns none on empty."""
    session, layout = _session_and_layout(tmp_path)
    command = MagicMock()
    command.execute = AsyncMock(return_value=SuccessResult(data={"results": []}))
    pos = await run_paginated_semantic(
        command=command,
        params={"project_id": "pid", "query": "q"},
        session=session,
        layout=layout,
        raw_config={},
        block_assembler_factory=_fake_assembler_factory,
    )
    assert pos is None
