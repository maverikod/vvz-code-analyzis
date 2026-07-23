"""Tests for paginated cross-search adapter (T-003/A-007)."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.search_mcp_command import SearchMCPCommand
from code_analysis.commands.search_paginated_cross import (
    _prefilter_candidates,
    indexed_finding_payload,
    normalize_cross_finding,
    run_paginated_cross,
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


def _fake_assembler_factory(
    layout,
    max_block_size_bytes,
    max_results_per_block=None,
    **kwargs: object,
):
    """Return fake assembler factory."""
    assembler = MagicMock()

    def run(search_completed=False):
        """Return run."""
        (layout.blocks_dir / "block_1.json").write_text(
            json.dumps({"position": 1, "items": []})
        )

    assembler.run_until_idle.side_effect = run
    return assembler


@pytest.mark.asyncio
async def test_prefilter_candidates_accepts_any_base_mcp_command_instance() -> None:
    """command: BaseMCPCommand (retyped off the deleted ProjectCrossSearchCommand) -
    any concrete BaseMCPCommand subclass works, since _prefilter_candidates only
    ever calls the inherited _resolve_project_root / _open_database_from_config.
    Proven here with SearchMCPCommand itself (the instance search_mcp_command.py
    now actually constructs), not a MagicMock."""
    command: BaseMCPCommand = SearchMCPCommand()

    with patch.object(
        BaseMCPCommand,
        "_resolve_project_root",
        side_effect=RuntimeError("no such project"),
    ):
        indexed, index_gap = _prefilter_candidates(
            command, "pid", logging.getLogger(__name__)
        )

    assert indexed == []
    assert index_gap == []


def test_indexed_finding_payload_fulltext_maps_content_and_score() -> None:
    """Verify test indexed finding payload fulltext maps content and score."""
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
    """Verify test normalize cross finding structural."""
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
    """Verify test normalize cross finding excludes line only when structural required."""
    raw = {"file_path": "c.py", "evidence": {"source_mode": "classic_line"}}
    finding = normalize_cross_finding(raw, index=0, require_structural_grep=True)
    assert finding is None


def test_normalize_cross_finding_includes_line_only_when_not_required() -> None:
    """Verify test normalize cross finding includes line only when not required."""
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
    """Verify test run paginated cross publishes block from fulltext."""
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
    """Verify test run paginated cross publishes block structural grep."""
    session, layout = _session_and_layout(tmp_path)
    command = MagicMock()
    command._resolve_project_root.return_value = tmp_path
    grep_cmd = MagicMock()

    async def _grep_execute(**kwargs: object) -> SuccessResult:
        """Return grep execute."""
        on_batch = kwargs.get("on_match_batch")
        if callable(on_batch):
            on_batch(
                [
                    {
                        "file_path": "c.py",
                        "evidence": {
                            "source_mode": "structural",
                            "node_ref": "node-1",
                        },
                    }
                ]
            )
        return SuccessResult(data={"matches": []})

    grep_cmd.execute = AsyncMock(side_effect=_grep_execute)
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
            "code_analysis.commands.search_paginated_cross.FsGrepCommand",
            return_value=grep_cmd,
        ),
    ):
        pos = await run_paginated_cross(
            command=command,
            params={
                "project_id": "pid",
                "query": "q",
                "enable_grep": True,
                "require_structural_grep": True,
            },
            session=session,
            layout=layout,
            raw_config={"search_session": {"max_block_size_bytes": 65536}},
            block_assembler_factory=_fake_assembler_factory,
        )
    assert pos == 1


@pytest.mark.asyncio
async def test_run_paginated_cross_global_fulltext_bypasses_command_class(
    tmp_path: Path,
) -> None:
    """project_id=None -> fulltext goes through domain.full_text_search_global
    directly (FulltextSearchMCPCommand, which hard-requires project_id, is never
    constructed for this path)."""
    session, layout = _session_and_layout(tmp_path)
    command = MagicMock()
    command._open_database_from_config.return_value = MagicMock(disconnect=MagicMock())

    global_rows = [
        {
            "file_path": "a.py",
            "content": "def foo(): pass",
            "bm25_score": 0.4,
            "entity_type": "function",
            "entity_name": "foo",
            "project_id": "proj-a",
            "project_name": "Project A",
        }
    ]

    with (
        patch(
            "code_analysis.core.database_driver_pkg.domain.search.full_text_search_global",
            return_value=global_rows,
        ) as ft_global_mock,
        patch(
            "code_analysis.commands.search_paginated_cross.FulltextSearchMCPCommand",
        ) as ft_cmd_class,
    ):
        pos = await run_paginated_cross(
            command=command,
            params={
                "project_id": None,
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
    ft_global_mock.assert_called_once()
    ft_cmd_class.assert_not_called()
    block_path = layout.blocks_dir / "block_1.json"
    data = json.loads(block_path.read_text(encoding="utf-8"))
    results = data.get("results") or data.get("items") or []
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_run_paginated_cross_global_semantic_skips_on_faiss_with_note(
    tmp_path: Path,
) -> None:
    """project_id=None + FAISS backend -> semantic phase skipped, a note is
    written to the session's notes.json explaining why (mirrors how grep
    phase-skips are reported via profile checkpoints, but this is
    client-visible)."""
    session, layout = _session_and_layout(tmp_path)
    command = MagicMock()
    command._open_database_from_config.return_value = MagicMock(disconnect=MagicMock())

    with (
        patch(
            "code_analysis.core.database_driver_pkg.domain.search.full_text_search_global",
            return_value=[],
        ),
        patch(
            "code_analysis.core.vector_search_backend.effective_vector_search_backend",
            return_value="faiss",
        ),
        patch(
            "code_analysis.core.storage_paths.load_raw_config",
            return_value={"code_analysis": {}},
        ),
        patch(
            "code_analysis.commands.base_mcp_command.BaseMCPCommand._resolve_config_path",
            return_value=tmp_path / "config.json",
        ),
    ):
        (tmp_path / "config.json").write_text("{}")
        pos = await run_paginated_cross(
            command=command,
            params={
                "project_id": None,
                "query": "foo",
                "enable_semantic": True,
                "semantic_limit": 5,
                "fulltext_limit": 0,
                "enable_grep": False,
                "grep_patterns": [],
            },
            session=session,
            layout=layout,
            raw_config={"search_session": {"max_block_size_bytes": 65536}},
        )

    # No fulltext (limit=0) and no semantic (skipped) -> no findings at all, so
    # no block gets published; this test's point is the note, not the block.
    assert pos is None
    notes_path = layout.root / "notes.json"
    assert notes_path.is_file()
    notes = json.loads(notes_path.read_text()).get("notes")
    assert notes and "FAISS" in notes[0]
    assert "pgvector" in notes[0]
