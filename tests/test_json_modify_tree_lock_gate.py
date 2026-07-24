"""
Tests for the project-exclusive-lock gate on ``json_modify_tree`` (bug 88f06abc
enforcement-gap audit).

``json_modify_tree`` never takes ``project_id`` in its schema at all -- it
mutates an in-memory JSON tree addressed purely by ``tree_id`` (obtained
earlier from ``json_load_file``). ``BaseMCPCommand.run()``'s literal-
``project_id`` gate can therefore never see it, so a project mid-rename
(exclusively locked) could still have its loaded tree mutated. The fix
resolves the owning project from the tree's own ``file_path`` (via the
``projectid`` marker file at its project root) and applies the same
``PROJECT_LOCKED`` check the gate uses, before any operation is applied.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.json_modify_tree_command import JsonModifyTreeCommand
from code_analysis.core.json_tree.tree_builder import build_tree_from_data, remove_tree

_PID = "550e8400-e29b-41d4-a716-446655440000"
_LOCK_ROW = {
    "project_id": _PID,
    "locked_at": 1.0,
    "owner": "rename_project:abc",
    "reason": "renaming",
}


@pytest.fixture
def loaded_tree(tmp_path: Path):
    """Register an in-memory JSON tree whose file lives under a project root
    carrying a ``projectid`` marker, mirroring what ``json_load_file`` leaves
    behind for a later ``json_modify_tree`` call in the same session."""
    (tmp_path / "projectid").write_text(json.dumps({"id": _PID}), encoding="utf-8")
    file_path = tmp_path / "config.json"
    file_path.write_text('{"a": 1}', encoding="utf-8")

    tree = build_tree_from_data(str(file_path), {"a": 1}, register=True)
    yield tree.tree_id
    remove_tree(tree.tree_id)


@pytest.mark.asyncio
async def test_locked_project_blocks_json_modify_tree(loaded_tree: str) -> None:
    """A locked owning project refuses the in-memory mutation with PROJECT_LOCKED."""
    cmd = JsonModifyTreeCommand()
    fake_db = MagicMock()

    with (
        patch.object(BaseMCPCommand, "_open_database_from_config", return_value=fake_db),
        patch(
            "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
            return_value=_LOCK_ROW,
        ) as mock_get_lock,
    ):
        result = await cmd.execute(
            tree_id=loaded_tree,
            operations=[{"action": "replace", "json_pointer": "/a", "value": 2}],
        )

    assert isinstance(result, ErrorResult)
    assert result.code == "PROJECT_LOCKED"
    mock_get_lock.assert_called_once_with(fake_db, _PID)


@pytest.mark.asyncio
async def test_unlocked_project_applies_json_modify_tree(loaded_tree: str) -> None:
    """An unlocked owning project applies the mutation as before the gap fix."""
    cmd = JsonModifyTreeCommand()
    fake_db = MagicMock()

    with (
        patch.object(BaseMCPCommand, "_open_database_from_config", return_value=fake_db),
        patch(
            "code_analysis.core.project_exclusive_lock.get_project_exclusive_lock",
            return_value=None,
        ),
    ):
        result = await cmd.execute(
            tree_id=loaded_tree,
            operations=[{"action": "replace", "json_pointer": "/a", "value": 2}],
        )

    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    assert result.data["success"] is True
