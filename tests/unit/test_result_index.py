"""Unit tests for SearchResultIndex persistence."""

from __future__ import annotations

import json
import uuid

import pytest

from code_analysis.core.search_session.directory import (
    provision_search_session_directory,
)
from code_analysis.core.search_session.result_index import (
    COMPLETENESS_FINISHED,
    COMPLETENESS_RUNNING,
    SearchResultIndex,
    append_block_entry,
    mark_index_finished,
    read_index,
)


def test_append_block_entry_preserves_order(tmp_path) -> None:
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        config_dir=tmp_path,
        search_id=search_id,
    )

    first = append_block_entry(
        layout.index_path,
        position=1,
        size_bytes=100,
        completeness=COMPLETENESS_RUNNING,
    )
    second = append_block_entry(
        layout.index_path,
        position=2,
        size_bytes=200,
        completeness=COMPLETENESS_RUNNING,
    )

    assert first.blocks == [{"position": 1, "size_bytes": 100}]
    assert second.blocks == [
        {"position": 1, "size_bytes": 100},
        {"position": 2, "size_bytes": 200},
    ]
    loaded = read_index(layout.index_path)
    assert loaded == SearchResultIndex(
        blocks=[
            {"position": 1, "size_bytes": 100},
            {"position": 2, "size_bytes": 200},
        ],
        completeness=COMPLETENESS_RUNNING,
    )


def test_mark_index_finished_sets_completeness_atomically(tmp_path) -> None:
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        config_dir=tmp_path,
        search_id=search_id,
    )
    append_block_entry(
        layout.index_path,
        position=1,
        size_bytes=50,
        completeness=COMPLETENESS_RUNNING,
    )

    finished = mark_index_finished(layout.index_path)

    assert finished.completeness == COMPLETENESS_FINISHED
    assert finished.blocks == [{"position": 1, "size_bytes": 50}]
    payload = json.loads(layout.index_path.read_text(encoding="utf-8"))
    assert payload["completeness"] == COMPLETENESS_FINISHED
    assert payload["blocks"] == [{"position": 1, "size_bytes": 50}]


def test_read_index_raises_when_missing(tmp_path) -> None:
    missing = tmp_path / "missing" / "index.json"
    with pytest.raises(FileNotFoundError):
        read_index(missing)
