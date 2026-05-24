"""Tests for paginated cross-search adapter (T-003/A-007)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from code_analysis.commands.search_paginated_cross import (
    normalize_cross_finding,
    run_paginated_cross,
)
from code_analysis.core.search_session.session import SearchSession, SearchSessionState
from mcp_proxy_adapter.commands.result import SuccessResult


def _session_and_layout(tmp_path: Path):
    from code_analysis.core.search_session.directory import provision_search_session_directory
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(config_dir=tmp_path, search_id=search_id)
    session = SearchSession(search_id=search_id, state=SearchSessionState.running, directory_path=layout.root)
    return session, layout


def _fake_assembler_factory(layout, raw_config):
    assembler = MagicMock()

    def run(search_completed=False):
        (layout.blocks_dir / "block_1.json").write_text(
            json.dumps({"position": 1, "items": []})
        )

    assembler.run_until_idle.side_effect = run
    return assembler


def test_normalize_cross_finding_structural() -> None:
    raw = {
        "file_path": "c.py",
        "confidence": "high",
        "evidence": {"source_mode": "structural"},
    }
    finding = normalize_cross_finding(raw, index=0, require_structural_grep=True)
    assert finding is not None
    assert finding["result_id"] == "cross-000000"
    assert finding["source"] == "cross"


def test_normalize_cross_finding_excludes_line_only_when_structural_required() -> None:
    raw = {"file_path": "c.py", "evidence": {"source_mode": "classic_line"}}
    finding = normalize_cross_finding(raw, index=0, require_structural_grep=True)
    assert finding is None


def test_normalize_cross_finding_includes_line_only_when_not_required() -> None:
    raw = {"file_path": "c.py", "evidence": {"source_mode": "classic_line"}}
    finding = normalize_cross_finding(raw, index=0, require_structural_grep=False)
    assert finding is not None


@pytest.mark.asyncio
async def test_run_paginated_cross_publishes_block(tmp_path: Path) -> None:
    session, layout = _session_and_layout(tmp_path)
    command = MagicMock()
    command.execute = AsyncMock(
        return_value=SuccessResult(data={"results": [
            {"file_path": "c.py", "evidence": {"source_mode": "structural"}, "confidence": "high"}
        ]})
    )
    pos = await run_paginated_cross(
        command=command,
        params={"project_id": "pid", "query": "q", "require_structural_grep": True},
        session=session,
        layout=layout,
        raw_config={},
        block_assembler_factory=_fake_assembler_factory,
    )
    assert pos == 1
