"""Unit tests for BlockAssembler."""

from __future__ import annotations

import json
import uuid

from code_analysis.core.search_session.block_assembler import (
    COMPLETENESS_RUNNING,
    BlockAssembler,
)
from code_analysis.core.search_session.directory import (
    provision_search_session_directory,
)
from code_analysis.core.search_session.raw_finding_buffer import RawFindingBuffer


def _make_assembler(
    tmp_path,
    *,
    max_block_size_bytes: int,
    append_index_entry=None,
    update_manifest_metrics=None,
):
    """Return make assembler."""
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        sessions_root=tmp_path / "search_sessions", search_id=search_id
    )
    buffer = RawFindingBuffer(layout.buffer_dir)
    index_entries: list[tuple[int, str]] = []
    metrics_updates: list[dict] = []

    assembler = BlockAssembler(
        layout,
        buffer,
        max_block_size_bytes,
        append_index_entry=append_index_entry
        or (
            lambda position, completeness: index_entries.append(
                (position, completeness)
            )
        ),
        update_manifest_metrics=update_manifest_metrics
        or (lambda metrics: metrics_updates.append(dict(metrics))),
    )
    return assembler, layout, buffer, index_entries, metrics_updates


def test_publishes_block_when_threshold_reached(tmp_path) -> None:
    """Verify test publishes block when threshold reached."""
    assembler, layout, buffer, index_entries, metrics_updates = _make_assembler(
        tmp_path,
        max_block_size_bytes=40,
    )
    buffer.append_finding("a", {"id": "a", "body": "1234567890"})
    buffer.append_finding("b", {"id": "b", "body": "1234567890"})

    published = assembler.run_once(search_completed=False)

    assert published == 1
    block_path = layout.blocks_dir / "block_1.json"
    assert block_path.is_file()
    payload = json.loads(block_path.read_text(encoding="utf-8"))
    assert len(payload["items"]) >= 1
    assert index_entries == [(1, COMPLETENESS_RUNNING)]
    assert metrics_updates[0]["written_blocks"] == 1
    assert buffer.lock_path.exists() is False


def test_final_run_drains_trailing_findings_and_releases_lock(tmp_path) -> None:
    """Verify test final run drains trailing findings and releases lock."""
    assembler, layout, buffer, index_entries, _metrics_updates = _make_assembler(
        tmp_path,
        max_block_size_bytes=10_000,
    )
    buffer.append_finding("tail", {"id": "tail", "value": 1})

    published = assembler.run_once(search_completed=True)

    assert published == 1
    assert (layout.blocks_dir / "block_1.json").is_file()
    assert index_entries == [(1, COMPLETENESS_RUNNING)]
    # _finalize() deletes buffer — verify the real side-effect
    assert buffer.buffer_dir.exists() is False
    assert buffer.lock_path.exists() is False


def test_exits_without_publishing_when_below_threshold_and_not_completed(
    tmp_path,
) -> None:
    """Verify test exits without publishing when below threshold and not completed."""
    assembler, layout, buffer, index_entries, metrics_updates = _make_assembler(
        tmp_path,
        max_block_size_bytes=10_000,
    )
    buffer.append_finding("small", {"id": "small"})

    published = assembler.run_once(search_completed=False)

    assert published == 0
    assert list(layout.blocks_dir.iterdir()) == []
    assert index_entries == []
    assert metrics_updates == []
    # buffer NOT finalized — it must still exist
    assert buffer.buffer_dir.exists() is True
    assert buffer.lock_path.exists() is False


def test_run_until_idle_accumulates_publications(tmp_path) -> None:
    """Verify test run until idle accumulates publications."""
    assembler, layout, buffer, index_entries, _metrics_updates = _make_assembler(
        tmp_path,
        max_block_size_bytes=10_000,
    )
    buffer.append_finding("only", {"id": "only"})

    total = assembler.run_until_idle(search_completed=True)

    assert total == 1
    assert (layout.blocks_dir / "block_1.json").is_file()
    assert index_entries == [(1, COMPLETENESS_RUNNING)]
    # _finalize() deletes buffer
    assert buffer.buffer_dir.exists() is False


def test_second_assembler_exits_when_live_lock_held(tmp_path) -> None:
    """Verify test second assembler exits when live lock held."""
    assembler, _layout, buffer, _index_entries, _metrics_updates = _make_assembler(
        tmp_path,
        max_block_size_bytes=10,
    )
    buffer.append_finding("a", {"id": "a", "payload": "x" * 20})
    buffer.append_finding("b", {"id": "b", "payload": "x" * 20})

    assert buffer.try_acquire_lock() is True
    try:
        published = assembler.run_once(search_completed=False)
    finally:
        buffer.release_lock()

    assert published == 0
