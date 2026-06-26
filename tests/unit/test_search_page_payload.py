"""Unit tests for temporal search page payload builder."""

from __future__ import annotations

from code_analysis.core.search_session.directory import (
    provision_search_session_directory,
)
from code_analysis.core.search_session.page_payload import temporal_page_payload


def test_temporal_page_payload_reads_block_items(tmp_path) -> None:
    """Verify test temporal page payload reads block items."""
    layout = provision_search_session_directory(
        sessions_root=tmp_path,
        search_id="job-1",
    )
    (layout.blocks_dir / "block_1.json").write_text(
        '{"position": 1, "items": [{"result_id": "a"}]}',
        encoding="utf-8",
    )

    payload = temporal_page_payload(
        layout=layout,
        job_id="job-1",
        block_position=1,
        search_still_running=True,
    )

    assert payload["items"] == [{"result_id": "a"}]
    assert payload["block_position"] == 1
    assert payload["has_more"] is True


def test_temporal_page_payload_empty_when_block_missing(tmp_path) -> None:
    """Verify test temporal page payload empty when block missing."""
    layout = provision_search_session_directory(
        sessions_root=tmp_path,
        search_id="job-2",
    )

    payload = temporal_page_payload(
        layout=layout,
        job_id="job-2",
        block_position=1,
        search_still_running=True,
    )

    assert payload["items"] == []
    assert payload["has_more"] is True
