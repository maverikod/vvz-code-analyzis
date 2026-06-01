"""Tests for paginated fs_grep (ggrep) adapter (T-003/A-008)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from code_analysis.commands.search_paginated_ggrep import (
    build_ggrep_backend_params,
    normalize_ggrep_match,
    run_paginated_ggrep,
)
from code_analysis.core.search_session.session import SearchSession, SearchSessionState
from mcp_proxy_adapter.commands.result import SuccessResult


def _session_and_layout(tmp_path: Path):
    from code_analysis.core.search_session.directory import (
        provision_search_session_directory,
    )

    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        config_dir=tmp_path, search_id=search_id
    )
    session = SearchSession(
        search_id=search_id,
        state=SearchSessionState.running,
        directory_path=layout.root,
    )
    return session, layout


def _fake_assembler_factory(layout, raw_config):
    assembler = MagicMock()

    def run(search_completed=False):
        (layout.blocks_dir / "block_1.json").write_text(
            json.dumps({"position": 1, "items": []})
        )

    assembler.run_until_idle.side_effect = run
    return assembler


def test_normalize_ggrep_match() -> None:
    raw = {
        "file_path": "d.py",
        "line_number": 5,
        "match_text": "grep hit",
        "node_ref": "node-1",
    }
    finding = normalize_ggrep_match(raw, index=2)
    assert finding is not None
    assert finding.result_id == "grep-000002"
    assert finding.source == "grep"
    assert finding.file_path == "d.py"


def test_build_ggrep_backend_params_structural_default() -> None:
    params = {"project_id": "pid", "query": "foo", "require_structural_grep": True}
    result = build_ggrep_backend_params(params)
    assert result["project_id"] == "pid"
    assert result["pattern"] == "foo"
    assert "fast_text_only" in result
    assert "enrich_blocks" in result


@pytest.mark.asyncio
async def test_run_paginated_ggrep_returns_1_on_matches(tmp_path: Path) -> None:
    session, layout = _session_and_layout(tmp_path)
    command = MagicMock()
    command.execute = AsyncMock(
        return_value=SuccessResult(
            data={"matches": [{"file_path": "d.py", "line_number": 1}]}
        )
    )
    pos = await run_paginated_ggrep(
        command=command,
        params={"project_id": "pid", "query": "foo", "require_structural_grep": True},
        session=session,
        layout=layout,
        raw_config={},
        block_assembler_factory=_fake_assembler_factory,
    )
    assert pos == 1
