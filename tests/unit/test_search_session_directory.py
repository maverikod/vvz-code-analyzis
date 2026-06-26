"""Unit tests for search session directory provisioning."""

from __future__ import annotations

import uuid

import pytest

from code_analysis.core.search_session.directory import (
    BLOCKS_DIRNAME,
    BUFFER_DIRNAME,
    MANIFEST_FILENAME,
    provision_search_session_directory,
)


def test_provision_search_session_directory_creates_layout(tmp_path) -> None:
    """Verify test provision search session directory creates layout."""
    search_id = str(uuid.uuid4())
    sessions_root = tmp_path / "search_sessions"
    layout = provision_search_session_directory(
        sessions_root=sessions_root,
        search_id=search_id,
    )

    assert layout.root.is_dir()
    assert layout.blocks_dir.is_dir()
    assert layout.buffer_dir.is_dir()
    assert layout.root.name == search_id
    assert layout.manifest_path.name == MANIFEST_FILENAME
    assert layout.blocks_dir.name == BLOCKS_DIRNAME
    assert layout.buffer_dir.name == BUFFER_DIRNAME
    assert sessions_root in layout.root.parents


def test_provision_search_session_directory_raises_when_exists(tmp_path) -> None:
    """Verify test provision search session directory raises when exists."""
    search_id = str(uuid.uuid4())
    provision_search_session_directory(
        sessions_root=tmp_path / "search_sessions", search_id=search_id
    )
    with pytest.raises(FileExistsError):
        provision_search_session_directory(
            sessions_root=tmp_path / "search_sessions", search_id=search_id
        )
