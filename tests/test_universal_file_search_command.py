"""Tests for universal_file_search command."""

from __future__ import annotations

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.universal_file_edit.format_group import resolve_format_group
from code_analysis.commands.universal_file_edit.search_command import (
    UniversalFileSearchCommand,
)
from code_analysis.commands.universal_file_edit.session import (
    create_session,
    release_session,
)
from code_analysis.core.cst_tree.tree_builder import load_file_to_tree, remove_tree


@pytest.mark.asyncio
async def test_universal_file_search_xpath_on_session_tree(tmp_path) -> None:
    """Verify test universal file search xpath on session tree."""
    src = "def foo() -> None:\n    pass\n\ndef bar() -> int:\n    return 1\n"
    path = tmp_path / "search_target.py"
    path.write_text(src, encoding="utf-8")
    tree = load_file_to_tree(str(path))
    descriptor = resolve_format_group(path)
    session = create_session(
        path.resolve(),
        descriptor,
        "search_target.py",
        tree_id=tree.tree_id,
    )
    cmd = UniversalFileSearchCommand()
    try:
        result = await cmd.execute(
            project_id="test-project",
            session_id=session.session_id,
            search_type="xpath",
            query='FunctionDef[name="bar"]',
            include_code=True,
        )
        assert isinstance(result, SuccessResult)
        data = result.data or {}
        assert data.get("total_matches") == 1
        match = (data.get("matches") or [])[0]
        assert match["name"] == "bar"
        assert match["node_ref"] == match["stable_id"]
        assert "return 1" in (match.get("code") or "")
        assert data.get("tree_id") == tree.tree_id
    finally:
        release_session(session.session_id)
        remove_tree(tree.tree_id)


@pytest.mark.asyncio
async def test_universal_file_search_rejects_missing_session() -> None:
    """Verify test universal file search rejects missing session."""
    cmd = UniversalFileSearchCommand()
    result = await cmd.execute(
        project_id="test-project",
        session_id="00000000-0000-4000-8000-000000000000",
        query="FunctionDef",
    )
    assert isinstance(result, ErrorResult)
    assert result.code == "SESSION_NOT_FOUND"
