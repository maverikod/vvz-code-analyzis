"""Tests for invalid-file preview and universal_file_write lockfile fix."""

from __future__ import annotations

from pathlib import Path
import json
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from code_analysis.commands.universal_file_edit.errors import FORMAT_INVALID_ON_OPEN
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.commands.universal_file_edit.session import get_session
from code_analysis.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from code_analysis.commands.universal_file_preview.budget import PreviewBudget
from code_analysis.commands.universal_file_preview.handlers.json_handler import (
    JsonFileHandler,
)
from code_analysis.commands.universal_file_preview.errors import PreviewError
from code_analysis.commands.universal_file_preview.handlers.python_marked_handler import (
    PythonMarkedTreeHandler,
)
from code_analysis.commands.universal_file_preview.marked_tree_navigation import (
    navigate_marked_tree,
)
from code_analysis.core.cst_tree.tree_builder import get_tree, remove_tree

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"


def _db_for(tmp: Path, project_id: str = _PROJECT_UUID) -> MagicMock:
    """Return db for."""
    m = MagicMock()
    row = {
        "id": project_id,
        "root_path": str(tmp.resolve()),
        "watch_dir_id": None,
        "name": "test-project",
    }
    m.select.return_value = [row]
    p = MagicMock()
    p.root_path = str(tmp.resolve())
    m.get_project.return_value = p
    return m


def _ensure_project_root(tmp: Path, project_id: str = _PROJECT_UUID) -> None:
    """Return ensure project root."""
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            json.dumps({"id": project_id}) + "\n",
            encoding="utf-8",
        )


def test_json_handler_invalid_returns_raw_source_node(tmp_path: Path) -> None:
    """Verify test json handler invalid returns raw source node."""
    bad = tmp_path / "broken.json"
    bad.write_text('{"a": ', encoding="utf-8")
    node = JsonFileHandler().open_root(
        str(bad), None, PreviewBudget(preview_lines=20, value_preview_len=120)
    )
    assert not isinstance(node, PreviewError)
    assert node.is_invalid is True
    assert node.node_ref == ""
    assert '{"a": ' in node.attributes["text"]
    assert "parse_error" in node.attributes


def test_python_invalid_returns_raw_source_via_marked_tree(tmp_path: Path) -> None:
    """Verify test python invalid returns raw source via marked tree."""
    _ensure_project_root(tmp_path)
    bad = tmp_path / "broken.py"
    bad.write_text("def f(\n", encoding="utf-8")
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=120, full_text_max_lines=200
    )
    result = navigate_marked_tree(
        {
            "project_root": tmp_path,
            "rel_file_path": "broken.py",
            "file_path": str(bad),
            "node_ref": None,
            "selector": None,
            "session_id": None,
        },
        budget,
    )
    assert not isinstance(result, PreviewError)
    assert result.focus_node.is_invalid is True
    assert "def f(" in result.focus_node.attributes["text"]


@pytest.mark.asyncio
async def test_open_does_not_preempt_write_preview_phase(tmp_path: Path) -> None:
    """First universal_file_write after open must be preview, not commit."""
    _ensure_project_root(tmp_path)
    rel = "sample.py"
    p = tmp_path / rel
    p.write_text(
        "def foo():\n    return 1\n",
        encoding="utf-8",
    )
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(opened, SuccessResult)
    sid = str(opened.data["session_id"])
    ed = UniversalFileEditCommand()
    tree_id: str | None = None
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        from code_analysis.commands.universal_file_edit.session import get_session

        sess = get_session(sid)
        tree_id = sess.tree_id
        tree = get_tree(tree_id or "")
        assert tree is not None
        stable = next(
            m.stable_id
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "foo"
        )
        await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            operations=[
                {
                    "type": "replace",
                    "node_ref": stable,
                    "code_lines": [
                        "def foo():\n",
                        "    return 2\n",
                    ],
                }
            ],
        )
        wr = UniversalFileWriteCommand()
        preview = await wr.execute(
            **wr.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
    assert isinstance(preview, SuccessResult)
    assert preview.data.get("phase") == "preview"
    diff = str(preview.data.get("diff", ""))
    assert "return 2" in diff
    if tree_id:
        remove_tree(tree_id)


@pytest.mark.asyncio
async def test_create_invalid_json_preview_returns_raw_text(
    tmp_path: Path,
) -> None:
    """End-to-end: create broken JSON, preview must surface raw source."""
    from code_analysis.commands.universal_file_preview_command import (
        UniversalFilePreviewCommand,
    )

    _ensure_project_root(tmp_path)
    rel = "broken.json"
    broken = '{"key": "value", broken'
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "file_path": rel,
                    "create": True,
                    "initial_content": broken,
                }
            )
        )
        assert isinstance(opened, SuccessResult)
        assert opened.data.get("is_invalid") is True
        sid = str(opened.data["session_id"])
        prev = UniversalFilePreviewCommand()
        result = await prev.execute(
            **prev.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "file_path": rel,
                    "session_id": sid,
                    "node_ref": "",
                }
            )
        )
    assert isinstance(result, SuccessResult)
    focus = result.data.get("focus", {})
    assert focus.get("is_invalid") is True
    assert broken in (focus.get("text") or "")
    assert focus.get("text") != "{}"
    assert focus.get("attributes", {}).get("parse_error")
    assert result.data.get("blocks")
    assert focus.get("attributes", {}).get("full_text") is True


@pytest.mark.asyncio
async def test_create_invalid_json_writes_raw_and_sets_is_invalid(
    tmp_path: Path,
) -> None:
    """create=True with invalid initial_content must persist raw bytes and flag session."""
    _ensure_project_root(tmp_path)
    rel = "new_broken.json"
    broken = '{"key": "value", broken'
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "file_path": rel,
                    "create": True,
                    "initial_content": broken,
                }
            )
        )
    assert isinstance(opened, SuccessResult)
    assert opened.data.get("created") is True
    assert opened.data.get("is_invalid") is True
    assert (tmp_path / rel).read_text(encoding="utf-8") == broken


@pytest.mark.asyncio
async def test_open_invalid_json_sets_is_invalid_and_allows_raw_edit(
    tmp_path: Path,
) -> None:
    """Verify test open invalid json sets is invalid and allows raw edit."""
    _ensure_project_root(tmp_path)
    rel = "broken.json"
    p = tmp_path / rel
    p.write_text('{"ok": true', encoding="utf-8")
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(opened, SuccessResult)
    assert opened.data.get("is_invalid") is True
    sid = str(opened.data["session_id"])
    fixed = '{"ok": true}\n'
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            operations=[{"type": "replace", "node_ref": "", "content": fixed}],
        )
        wr = UniversalFileWriteCommand()
        preview = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
        )
        assert isinstance(preview, SuccessResult)
        assert preview.data.get("phase") == "preview"
        commit = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            write_mode="commit",
        )
        assert isinstance(commit, SuccessResult)
        assert commit.data.get("phase") == "committed"
    assert p.read_text(encoding="utf-8") == fixed


def test_json_handler_invalid_preserves_broken_trailing_text(tmp_path: Path) -> None:
    """Broken JSON must surface raw bytes, not an empty object placeholder."""
    broken = '{"key": "value", broken'
    bad = tmp_path / "broken.json"
    bad.write_text(broken, encoding="utf-8")
    node = JsonFileHandler().open_root(
        str(bad), None, PreviewBudget(preview_lines=20, value_preview_len=120)
    )
    assert not isinstance(node, PreviewError)
    assert node.is_invalid is True
    assert node.attributes.get("text") == broken
    assert node.attributes.get("full_text") is True
    assert "{}" not in node.attributes.get("text", "")


@pytest.mark.asyncio
async def test_preview_broken_json_with_uuid_node_ref_requires_line_addressing(
    tmp_path: Path,
) -> None:
    """UUID node_ref on invalid JSON must not drill; use line pagination instead."""
    from code_analysis.commands.universal_file_preview.errors import (
        INPUT_ERROR_REQUIRES_LINE_ADDRESSING,
    )
    from code_analysis.commands.universal_file_preview_command import (
        UniversalFilePreviewCommand,
    )

    _ensure_project_root(tmp_path)
    broken = '{"key": "value", broken'
    rel = "broken.json"
    (tmp_path / rel).write_text(broken, encoding="utf-8")
    prev = UniversalFilePreviewCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        result = await prev.execute(
            **prev.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "file_path": rel,
                    "node_ref": "3aeb19cf-4a9d-45d6-b3af-a0e4975bf874",
                }
            )
        )
    assert isinstance(result, ErrorResult)
    assert result.code == INPUT_ERROR_REQUIRES_LINE_ADDRESSING


@pytest.mark.asyncio
async def test_open_invalid_yaml_sets_is_invalid_and_warning(tmp_path: Path) -> None:
    """Verify test open invalid yaml sets is invalid and warning."""
    _ensure_project_root(tmp_path)
    rel = "broken.yaml"
    (tmp_path / rel).write_text("key: [unclosed\n", encoding="utf-8")
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(opened, SuccessResult)
    assert opened.data.get("is_invalid") is True
    assert opened.data.get("warning")
    assert "line-based fallback" in str(opened.data.get("warning"))


@pytest.mark.asyncio
async def test_open_invalid_py_falls_back_to_text(tmp_path: Path) -> None:
    """Verify test open invalid py falls back to text."""
    _ensure_project_root(tmp_path)
    rel = "broken.py"
    (tmp_path / rel).write_text("def f(\n", encoding="utf-8")
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(opened, SuccessResult)
    assert opened.data.get("is_invalid") is True
    assert opened.data.get("warning")


@pytest.mark.asyncio
async def test_edit_invalid_session_returns_warning(tmp_path: Path) -> None:
    """Verify test edit invalid session returns warning."""
    _ensure_project_root(tmp_path)
    rel = "broken.json"
    (tmp_path / rel).write_text('{"a": ', encoding="utf-8")
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(opened, SuccessResult)
    sid = str(opened.data["session_id"])
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        result = await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            operations=[{"type": "replace", "node_ref": "", "content": '{"a": 1}\n'}],
        )
    assert isinstance(result, SuccessResult)
    assert result.data.get("warning")
    assert "line-based fallback" in str(result.data.get("warning"))


@pytest.mark.asyncio
async def test_write_commit_invalid_session_still_broken_returns_error(
    tmp_path: Path,
) -> None:
    """Verify test write commit invalid session still broken returns error."""
    _ensure_project_root(tmp_path)
    rel = "broken.json"
    (tmp_path / rel).write_text('{"a": ', encoding="utf-8")
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    sid = str(opened.data["session_id"])
    ed = UniversalFileEditCommand()
    wr = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            operations=[{"type": "replace", "node_ref": "", "content": '{"still": '}],
        )
        commit = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            write_mode="commit",
        )
    assert isinstance(commit, ErrorResult)
    assert commit.code == FORMAT_INVALID_ON_OPEN
    assert commit.details is not None
    assert commit.details.get("parse_errors")


@pytest.mark.asyncio
async def test_write_commit_invalid_session_fixed_restores_structural_editing(
    tmp_path: Path,
) -> None:
    """Verify test write commit invalid session fixed restores structural editing."""
    _ensure_project_root(tmp_path)
    rel = "broken.json"
    p = tmp_path / rel
    p.write_text('{"ok": true', encoding="utf-8")
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    sid = str(opened.data["session_id"])
    fixed = '{"ok": true}\n'
    ed = UniversalFileEditCommand()
    wr = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await ed.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            operations=[{"type": "replace", "node_ref": "", "content": fixed}],
        )
        commit = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            write_mode="commit",
        )
    assert isinstance(commit, SuccessResult)
    assert commit.data.get("structural_editing_restored") is True
    assert commit.data.get("is_invalid") is False
    sess = get_session(sid)
    assert sess.format_group == "tree-temp"
    assert sess.is_invalid is False
    assert p.read_text(encoding="utf-8") == fixed


@pytest.mark.asyncio
async def test_write_preview_invalid_session_always_succeeds(tmp_path: Path) -> None:
    """Verify test write preview invalid session always succeeds."""
    _ensure_project_root(tmp_path)
    rel = "broken.json"
    (tmp_path / rel).write_text('{"a": ', encoding="utf-8")
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        opened = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    sid = str(opened.data["session_id"])
    wr = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        preview = await wr.execute(
            project_id=_PROJECT_UUID,
            session_id=sid,
            write_mode="preview",
        )
    assert isinstance(preview, SuccessResult)
    assert preview.data.get("phase") == "preview"
