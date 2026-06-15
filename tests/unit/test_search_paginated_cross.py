"""Tests for paginated cross-search adapter (T-003/A-007)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.search_paginated_cross import (
    indexed_finding_payload,
    normalize_cross_finding,
    run_paginated_cross,
)
from code_analysis.core.search_session.session import SearchSession, SearchSessionState
from mcp_proxy_adapter.commands.result import SuccessResult


def _session_and_layout(tmp_path: Path):
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


def _fake_assembler_factory(layout, max_block_size_bytes, max_results_per_block=None):
    assembler = MagicMock()

    def run(search_completed=False):
        (layout.blocks_dir / "block_1.json").write_text(
            json.dumps({"position": 1, "items": []})
        )

    assembler.run_until_idle.side_effect = run
    return assembler


def test_indexed_finding_payload_fulltext_maps_content_and_score() -> None:
    raw = {
        "file_path": "src/mod.py",
        "content": "def foo() -> int:\n    return 1",
        "bm25_score": 0.2,
        "entity_type": "function",
        "entity_name": "foo",
    }
    payload = indexed_finding_payload(raw, index=3, source="fulltext")
    assert payload["result_id"] == "fulltext-000003"
    assert payload["source"] == "fulltext"
    assert payload["text"] == raw["content"]
    assert payload["score"] == 0.2


def test_normalize_cross_finding_structural() -> None:
    raw = {
        "file_path": "c.py",
        "confidence": "high",
        "evidence": {"source_mode": "structural", "node_ref": "node-1"},
    }
    finding = normalize_cross_finding(raw, index=0, require_structural_grep=True)
    assert finding is not None
    assert finding.result_id == "cross-000000"
    assert finding.source == "cross"


def test_normalize_cross_finding_excludes_line_only_when_structural_required() -> None:
    raw = {"file_path": "c.py", "evidence": {"source_mode": "classic_line"}}
    finding = normalize_cross_finding(raw, index=0, require_structural_grep=True)
    assert finding is None


def test_normalize_cross_finding_includes_line_only_when_not_required() -> None:
    raw = {
        "file_path": "c.py",
        "evidence": {"source_mode": "classic_line", "node_ref": "node-1"},
    }
    finding = normalize_cross_finding(raw, index=0, require_structural_grep=False)
    assert finding is not None


@pytest.mark.asyncio
async def test_run_paginated_cross_publishes_block_from_fulltext(
    tmp_path: Path,
) -> None:
    session, layout = _session_and_layout(tmp_path)
    command = MagicMock()
    command._resolve_project_root.return_value = tmp_path
    command._open_database_from_config.side_effect = RuntimeError("skip prefilter db")

    ft_result = SuccessResult(
        data={
            "results": [
                {
                    "file_path": "c.py",
                    "content": "def foo(): pass",
                    "bm25_score": 0.3,
                    "entity_type": "function",
                    "entity_name": "foo",
                }
            ]
        }
    )
    sem_mock = MagicMock()
    sem_mock.execute = AsyncMock(return_value=SuccessResult(data={"results": []}))
    ft_mock = MagicMock()
    ft_mock.execute = AsyncMock(return_value=ft_result)

    with (
        patch(
            "code_analysis.commands.search_paginated_cross.SemanticSearchMCPCommand",
            return_value=sem_mock,
        ),
        patch(
            "code_analysis.commands.search_paginated_cross.FulltextSearchMCPCommand",
            return_value=ft_mock,
        ),
        patch(
            "code_analysis.commands.search_paginated_cross._prefilter_candidates",
            return_value=([], []),
        ),
    ):
        pos = await run_paginated_cross(
            command=command,
            params={
                "project_id": "pid",
                "query": "foo",
                "semantic_limit": 0,
                "enable_grep": False,
                "grep_patterns": [],
            },
            session=session,
            layout=layout,
            raw_config={"search_session": {"max_block_size_bytes": 65536}},
        )

    assert pos == 1
    block_path = layout.blocks_dir / "block_1.json"
    assert block_path.is_file()
    data = json.loads(block_path.read_text(encoding="utf-8"))
    results = data.get("results") or data.get("items") or []
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_run_paginated_cross_publishes_block_structural_grep(
    tmp_path: Path,
) -> None:
    session, layout = _session_and_layout(tmp_path)
    command = MagicMock()
    command._resolve_project_root.return_value = tmp_path
    grep_cmd = MagicMock()
    grep_cmd.execute = AsyncMock(
        return_value=SuccessResult(
            data={
                "matches": [
                    {
                        "file_path": "c.py",
                        "evidence": {
                            "source_mode": "structural",
                            "node_ref": "node-1",
                        },
                    }
                ]
            }
        )
    )
    sem_mock = MagicMock()
    sem_mock.execute = AsyncMock(return_value=SuccessResult(data={"results": []}))
    ft_mock = MagicMock()
    ft_mock.execute = AsyncMock(return_value=SuccessResult(data={"results": []}))

    with (
        patch(
            "code_analysis.commands.search_paginated_cross.SemanticSearchMCPCommand",
            return_value=sem_mock,
        ),
        patch(
            "code_analysis.commands.search_paginated_cross.FulltextSearchMCPCommand",
            return_value=ft_mock,
        ),
        patch(
            "code_analysis.commands.search_paginated_cross._prefilter_candidates",
            return_value=([], []),
        ),
        patch(
            "code_analysis.commands.search_paginated_cross.FsGrepCommand",
            return_value=grep_cmd,
        ),
    ):
        pos = await run_paginated_cross(
            command=command,
            params={"project_id": "pid", "query": "q", "enable_grep": True, "require_structural_grep": True},
            session=session,
            layout=layout,
            raw_config={"search_session": {"max_block_size_bytes": 65536}},
            block_assembler_factory=_fake_assembler_factory,
        )
    assert pos == 1
