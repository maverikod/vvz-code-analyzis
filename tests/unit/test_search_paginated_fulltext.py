"""Tests for paginated fulltext adapter (T-003/A-005)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_analysis.commands.search_paginated_fulltext import (
    normalize_fulltext_finding,
    run_paginated_fulltext,
)
from code_analysis.core.search_session.session import SearchSession, SearchSessionState
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult


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


def _fake_assembler_factory(layout, raw_config) -> MagicMock:
    """Return fake assembler factory."""
    assembler = MagicMock()

    def run_until_idle(search_completed=False):
        """Return run until idle."""
        block_path = layout.blocks_dir / "block_1.json"
        block_path.write_text(json.dumps({"position": 1, "items": []}))

    assembler.run_until_idle.side_effect = run_until_idle
    return assembler


def test_normalize_fulltext_finding_maps_fields() -> None:
    """Verify test normalize fulltext finding maps fields."""
    raw = {"file_path": "src/a.py", "chunk_text": "hello", "rank": 0.5, "line": 10}
    finding = normalize_fulltext_finding(raw, index=3)
    assert finding["result_id"] == "fulltext-000003"
    assert finding["source"] == "fulltext"
    assert finding["file_path"] == "src/a.py"
    assert finding["text"] == "hello"


def test_normalize_fulltext_finding_maps_current_backend_row_shape() -> None:
    """Current full_text_search rows use ``content`` + ``bm25_score``."""
    raw = {
        "file_path": "src/a.py",
        "content": "def hello() -> None:\n    pass",
        "bm25_score": 0.75,
        "line": 10,
        "entity_type": "function",
        "entity_name": "hello",
    }
    finding = normalize_fulltext_finding(raw, index=4)
    assert finding["result_id"] == "fulltext-000004"
    assert finding["text"] == raw["content"]
    assert finding["score"] == raw["bm25_score"]
    assert finding["entity_type"] == "function"
    assert finding["entity_name"] == "hello"


def test_normalize_fulltext_finding_carries_project_attribution() -> None:
    """Bug 29212ab2: project_id/project_name from the backend SELECT (both the
    per-project and global(project_id=None) rows already carry them) must
    survive normalization into the finding row, not be silently dropped."""
    raw = {
        "file_path": "src/a.py",
        "chunk_text": "hello",
        "rank": 0.5,
        "project_id": "proj-a",
        "project_name": "Project A",
    }
    finding = normalize_fulltext_finding(raw, index=0)
    assert finding["project_id"] == "proj-a"
    assert finding["project_name"] == "Project A"


def test_normalize_fulltext_finding_project_attribution_absent_is_none() -> None:
    """Per-project backend rows that never carried project_id (older/mocked
    shape) must not error - the field is simply None, not KeyError."""
    raw = {"file_path": "src/a.py", "chunk_text": "hello"}
    finding = normalize_fulltext_finding(raw, index=0)
    assert finding["project_id"] is None
    assert finding["project_name"] is None


def test_normalize_fulltext_finding_coerces_uuid_project_id_to_str() -> None:
    """Regression for the N3 fallout: real Postgres backend SELECTs return
    ``project_id`` as an actual ``uuid.UUID`` object, not str. Carrying it
    through verbatim (as commit 813ba061 did) makes the downstream
    ``json.dump`` in ``RawFindingBuffer.append_finding`` crash with
    ``TypeError: Object of type UUID is not JSON serializable`` and kill the
    whole search job. The normalizer must coerce to str while keeping the
    attribution populated."""
    project_id = uuid.uuid4()
    raw = {
        "file_path": "src/a.py",
        "chunk_text": "hello",
        "project_id": project_id,
        "project_name": "Project A",
    }
    finding = normalize_fulltext_finding(raw, index=0)
    assert finding["project_id"] == str(project_id)
    assert isinstance(finding["project_id"], str)
    assert finding["project_name"] == "Project A"


@pytest.mark.asyncio
async def test_run_paginated_fulltext_publishes_block_and_returns_1(
    tmp_path: Path,
) -> None:
    """Verify test run paginated fulltext publishes block and returns 1."""
    session, layout = _session_and_layout(tmp_path)

    command = MagicMock()
    command.execute = AsyncMock(
        return_value=SuccessResult(
            data={"results": [{"file_path": "a.py", "chunk_text": "x"}], "count": 1}
        )
    )

    pos = await run_paginated_fulltext(
        command=command,
        params={"project_id": "pid", "query": "x", "paginated": True},
        session=session,
        layout=layout,
        raw_config={},
        block_assembler_factory=_fake_assembler_factory,
    )
    assert pos == 1


@pytest.mark.asyncio
async def test_run_paginated_fulltext_error_raises(tmp_path: Path) -> None:
    """Verify test run paginated fulltext error raises."""
    session, layout = _session_and_layout(tmp_path)

    command = MagicMock()
    command.execute = AsyncMock(return_value=ErrorResult(message="boom", code="ERR"))

    with pytest.raises(RuntimeError, match="boom"):
        await run_paginated_fulltext(
            command=command,
            params={"project_id": "pid", "query": "x"},
            session=session,
            layout=layout,
            raw_config={},
            block_assembler_factory=_fake_assembler_factory,
        )
