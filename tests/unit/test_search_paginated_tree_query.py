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


def _session(tmp_path: Path) -> SearchSession:
    search_id = str(uuid.uuid4())
    root = tmp_path / search_id
    root.mkdir(parents=True)
    return SearchSession(
        search_id=search_id, state=SearchSessionState.running, directory_path=root
    )


def _layout(tmp_path: Path, session: SearchSession):
    from code_analysis.core.search_session.directory import SearchSessionDirectoryLayout

    root = session.directory_path
    (root / "blocks").mkdir(exist_ok=True)
    (root / "buffer").mkdir(exist_ok=True)
    return SearchSessionDirectoryLayout(root=root)


def _fake_assembler_factory(layout, raw_config):
    assembler = MagicMock()

    def run(search_completed=False):
        (layout.blocks_dir / "block_1.json").write_text(
            json.dumps({"position": 1, "items": []})
        )

    assembler.run_until_idle.side_effect = run
    return assembler


def test_normalize_tree_query_finding() -> None:
    raw = {
        "file_path": "e.py",
        "start_line": 10,
        "end_line": 20,
        "stable_id": "node-1",
        "xpath": "//FunctionDef",
    }
    finding = normalize_tree_query_finding(raw, index=5)
    assert finding["result_id"] == "tree_query-000005"
    assert finding["source"] == "tree_query"
    assert finding["file_path"] == "e.py"
    assert finding["node_ref"] == "node-1"
    assert finding["selector"] == "//FunctionDef"


@pytest.mark.asyncio
async def test_run_paginated_tree_query_returns_1_on_matches(tmp_path: Path) -> None:
    session = _session(tmp_path)
    layout = _layout(tmp_path, session)

    def scanner(xpath, file_pattern, project_id):
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
    session = _session(tmp_path)
    layout = _layout(tmp_path, session)

    pos = await run_paginated_tree_query(
        params={"project_id": "pid", "xpath": "//FunctionDef"},
        session=session,
        layout=layout,
        raw_config={},
        block_assembler_factory=_fake_assembler_factory,
        tree_scanner=lambda **kw: [],
    )
    assert pos is None
