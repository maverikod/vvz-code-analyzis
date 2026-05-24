"""Unit tests for search session directory provisioning."""

from __future__ import annotations

import uuid

import pytest

from code_analysis.core.search_session.directory import (
    BLOCKS_DIRNAME,
    BUFFER_DIRNAME,
    MANIFEST_FILENAME,
    provision_search_session_directory,
    resolve_search_sessions_root,
)


def test_provision_search_session_directory_creates_layout(tmp_path) -> None:
    search_id = str(uuid.uuid4())
    layout = provision_search_session_directory(
        config_dir=tmp_path,
        search_id=search_id,
    )

    assert layout.root.is_dir()
    assert layout.blocks_dir.is_dir()
    assert layout.buffer_dir.is_dir()
    assert layout.root.name == search_id
    assert layout.manifest_path.name == MANIFEST_FILENAME
    assert layout.blocks_dir.name == BLOCKS_DIRNAME
    assert layout.buffer_dir.name == BUFFER_DIRNAME
    assert resolve_search_sessions_root(tmp_path) in layout.root.parents


def test_provision_search_session_directory_raises_when_exists(tmp_path) -> None:
    search_id = str(uuid.uuid4())
    provision_search_session_directory(config_dir=tmp_path, search_id=search_id)
    with pytest.raises(FileExistsError):
        provision_search_session_directory(config_dir=tmp_path, search_id=search_id)
