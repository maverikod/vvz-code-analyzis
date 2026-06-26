"""Tests for paginated tree_query adapter (T-003/A-009)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from code_analysis.commands.search_paginated_tree_query import (
    normalize_tree_query_finding,
    run_paginated_tree_query,
)
from code_analysis.core.search_session.session import SearchSession, SearchSessionState


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


def test_normalize_tree_query_finding() -> None:
    """Verify test normalize tree query finding."""
    raw = {
        "file_path": "e.py",
        "start_line": 10,
        "end_line": 20,
        "stable_id": "node-1",
        "xpath": "//FunctionDef",
    }
    finding = normalize_tree_query_finding(raw, index=5)
    assert finding is not None
    assert finding.result_id == "tree_query-000005"
    assert finding.source == "tree_query"
    assert finding.file_path == "e.py"
    assert finding.stable_id == "node-1"


@pytest.mark.asyncio
async def test_run_paginated_tree_query_returns_1_on_matches(tmp_path: Path) -> None:
    """Verify test run paginated tree query returns 1 on matches."""
    session, layout = _session_and_layout(tmp_path)

    def scanner(xpath, file_pattern, project_id):
        """Return scanner."""
        return [
            {"file_path": "e.py", "start_line": 1, "end_line": 5, "stable_id": "n1"}
        ]

    pos = await run_paginated_tree_query(
        params={"project_id": "pid", "xpath": "//FunctionDef", "paginated": True},
        session=session,
        layout=layout,
        raw_config={},
        block_assembler_factory=_fake_assembler_factory,
        tree_scanner=scanner,
    )
    assert pos == 1


@pytest.mark.asyncio
async def test_run_paginated_tree_query_returns_none_on_empty(tmp_path: Path) -> None:
    """Verify test run paginated tree query returns none on empty."""
    session, layout = _session_and_layout(tmp_path)

    pos = await run_paginated_tree_query(
        params={"project_id": "pid", "xpath": "//FunctionDef"},
        session=session,
        layout=layout,
        raw_config={},
        block_assembler_factory=_fake_assembler_factory,
        tree_scanner=lambda **kw: [],
    )
    assert pos is None
