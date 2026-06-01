"""
Integration tests for session_write two-stage external copy-out (C-012).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from collections.abc import Generator
from pathlib import Path

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.universal_file_edit.errors import SESSION_NOT_FOUND
from code_analysis.commands.universal_file_edit.session_write_command import (
    SessionWriteCommand,
)
from code_analysis.core.edit_session.edit_session import EditSession
from code_analysis.core.tree_lifecycle.builder import TreeBuilder
from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum
from code_analysis.tree.sibling_convention import sibling_tree_path

PROJECT_ID = "00000000-0000-0000-0000-000000000014"
REL = "write/demo.json"
INITIAL_JSON = '{"n": 1}\n'


def _sha_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def open_mutated_session(tmp_path: Path) -> Generator[EditSession, None, None]:
    source_abs = tmp_path / REL
    source_abs.parent.mkdir(parents=True, exist_ok=True)
    source_abs.write_text(INITIAL_JSON, encoding="utf-8")
    TreeBuilder.build(
        content=INITIAL_JSON,
        source_abs=source_abs,
        file_path=REL,
        content_checksum=compute_content_checksum(INITIAL_JSON),
    )
    session = EditSession.open(
        source_abs=source_abs,
        project_root=tmp_path,
        file_path=REL,
    )
    session.apply_valid_tree_mutation(lambda t: t.replace('"n": 1', '"n": 99'))
    try:
        yield session
    finally:
        session.close()


@pytest.mark.asyncio
async def test_preview_does_not_modify_external_files(
    tmp_path: Path,
    open_mutated_session: EditSession,
) -> None:
    session = open_mutated_session
    source = tmp_path / REL
    tree = sibling_tree_path(source)
    source_hash_before = _sha_hex(source)
    tree_hash_before = _sha_hex(tree)

    cmd = SessionWriteCommand()
    res = await cmd.execute(
        project_id=PROJECT_ID,
        session_id=session.session_id,
        confirm=False,
    )

    assert isinstance(res, SuccessResult)
    assert res.data["phase"] == "preview"
    assert res.data["has_changes"] is True
    assert "source_diff" in res.data
    assert res.data["source_diff"]
    assert _sha_hex(source) == source_hash_before
    assert _sha_hex(tree) == tree_hash_before
    assert '"n": 1' in source.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_confirm_copies_when_confirm_true(
    tmp_path: Path,
    open_mutated_session: EditSession,
) -> None:
    session = open_mutated_session
    cmd = SessionWriteCommand()

    preview_res = await cmd.execute(
        project_id=PROJECT_ID,
        session_id=session.session_id,
        confirm=False,
    )
    assert isinstance(preview_res, SuccessResult)
    assert preview_res.data["has_changes"] is True

    confirm_res = await cmd.execute(
        project_id=PROJECT_ID,
        session_id=session.session_id,
        confirm=True,
    )

    assert isinstance(confirm_res, SuccessResult)
    assert confirm_res.data["phase"] == "confirmed"
    assert '"n": 99' in (tmp_path / REL).read_text(encoding="utf-8")

    tree = sibling_tree_path((tmp_path / REL).resolve())
    assert tree.is_file()
    assert "---TREE---" in tree.read_text(encoding="utf-8")
    assert _sha_hex(session.session_source_path) == _sha_hex(tmp_path / REL)


@pytest.mark.asyncio
async def test_missing_session_id_errors(tmp_path: Path) -> None:
    _ = tmp_path
    res = await SessionWriteCommand().execute(
        project_id=PROJECT_ID,
        session_id="00000000-0000-4000-8000-000000000088",
    )
    assert isinstance(res, ErrorResult)
    assert res.code == SESSION_NOT_FOUND
