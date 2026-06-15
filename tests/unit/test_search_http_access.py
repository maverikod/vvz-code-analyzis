"""Unit tests for search job HTTP access handlers."""

from __future__ import annotations

import time
import uuid

from code_analysis.core.search_session.directory import (
    provision_search_session_directory,
)
from code_analysis.core.search_session.http_access import (
    BLOCK_NOT_READY,
    HttpAccessContext,
    SESSION_NOT_FOUND,
    handle_get_block,
    handle_get_index,
    handle_get_status,
)
from code_analysis.core.search_session.manifest import (
    SearchSessionManifest,
    ServerProcessIdentity,
    write_manifest_atomic,
)
from code_analysis.core.search_session.result_block import (
    SearchResultBlock,
    serialize_block,
)
from code_analysis.core.search_session.result_index import (
    COMPLETENESS_RUNNING,
    append_block_entry,
)
from code_analysis.core.search_session.service_metadata import (
    initialize_service_metadata,
    read_service_metadata,
)


def _write_manifest(
    layout, *, status: str = "running", phase: str = "block_writing"
) -> None:
    now = time.time()
    manifest = SearchSessionManifest(
        search_id=layout.root.name,
        created_at=now,
        last_access_at=now,
        heartbeat_at=now,
        status=status,
        phase=phase,
        request={"query": "test"},
        metrics={"written_blocks": 1, "produced_results": 1},
        process=ServerProcessIdentity(main_pid=1, process_start_time=now),
        block_ready_count=1,
    )
    write_manifest_atomic(layout, manifest)


def test_handle_get_index_refreshes_service_metadata(tmp_path) -> None:
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        sessions_root=tmp_path / "search_sessions", search_id=search_id
    )
    initial = time.time() - 100.0
    initialize_service_metadata(layout, now=initial)
    append_block_entry(
        layout.index_path,
        position=1,
        size_bytes=10,
        completeness=COMPLETENESS_RUNNING,
    )
    ctx = HttpAccessContext(sessions_root=tmp_path / "search_sessions")

    status_code, payload = handle_get_index(ctx, search_id)

    assert status_code == 200
    assert payload["blocks"] == [{"position": 1, "size_bytes": 10}]
    assert payload["completeness"] == COMPLETENESS_RUNNING
    refreshed = read_service_metadata(layout)
    assert refreshed.last_access_at > initial


def test_handle_get_block_returns_block_not_ready_for_unpublished_position(
    tmp_path,
) -> None:
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        sessions_root=tmp_path / "search_sessions", search_id=search_id
    )
    append_block_entry(
        layout.index_path,
        position=1,
        size_bytes=10,
        completeness=COMPLETENESS_RUNNING,
    )
    ctx = HttpAccessContext(sessions_root=tmp_path / "search_sessions")

    status_code, payload = handle_get_block(ctx, search_id, 2)

    assert status_code == 409
    assert payload["error"]["code"] == BLOCK_NOT_READY


def test_handle_get_block_returns_published_block(tmp_path) -> None:
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        sessions_root=tmp_path / "search_sessions", search_id=search_id
    )
    append_block_entry(
        layout.index_path,
        position=1,
        size_bytes=10,
        completeness=COMPLETENESS_RUNNING,
    )
    block = SearchResultBlock(
        position=1, results=({"id": "a"},), serialized_size_bytes=0
    )
    block_path = layout.blocks_dir / "block_1.json"
    block_path.write_bytes(serialize_block(block))
    ctx = HttpAccessContext(sessions_root=tmp_path / "search_sessions")

    status_code, payload = handle_get_block(ctx, search_id, 1)

    assert status_code == 200
    assert payload["position"] == 1
    assert payload["results"] == [{"id": "a"}]


def test_handle_get_status_reads_manifest_and_refreshes_access(tmp_path) -> None:
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        sessions_root=tmp_path / "search_sessions", search_id=search_id
    )
    _write_manifest(layout, status="running", phase="indexed_search")
    initial = time.time() - 50.0
    initialize_service_metadata(layout, now=initial)
    ctx = HttpAccessContext(sessions_root=tmp_path / "search_sessions")

    status_code, payload = handle_get_status(ctx, search_id)

    assert status_code == 200
    assert payload["status"] == "running"
    assert payload["phase"] == "indexed_search"
    assert payload["metrics"]["written_blocks"] == 1
    assert read_service_metadata(layout).last_access_at > initial


def test_handle_get_index_returns_not_found_for_missing_session(tmp_path) -> None:
    ctx = HttpAccessContext(sessions_root=tmp_path / "search_sessions")

    status_code, payload = handle_get_index(ctx, str(uuid.uuid4()))

    assert status_code == 404
    assert payload["error"]["code"] == SESSION_NOT_FOUND
