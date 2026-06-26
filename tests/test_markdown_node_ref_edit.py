"""Markdown node_ref line ranges: preview attributes and text edit by node_ref."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from markdown_it import MarkdownIt
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from code_analysis.commands.universal_file_preview.budget import PreviewBudget
from code_analysis.commands.universal_file_preview.handlers.markdown_handler import (
    MarkdownFileHandler,
)
from code_analysis.commands.universal_file_preview.handlers.markdown_line_ranges import (
    md_block_node_ref,
)
from code_analysis.commands.universal_file_preview.navigation import navigate
from code_analysis.commands.universal_file_preview.response import build_envelope
from code_analysis.commands.universal_file_read_command import (
    UniversalFileReadCommand,
)

_PROJECT_UUID = "baadf00d-baad-4bad-b00d-baaaaaaaaaaa"

_LEAF_SECTION = """\
# Only Section

This section has body text but no sub-sections.
"""

_PARENT_WITH_SUBS = """\
# Parent

Parent body paragraph here.

## Sub One

Sub one body.

## Sub Two

Sub two body.
"""


def _section_tree_budget() -> PreviewBudget:
    """Return section tree budget."""
    return PreviewBudget(
        preview_lines=20,
        value_preview_len=120,
        full_text_max_lines=0,
    )


def _preview_md(tmp_path: Path, content: str, node_ref: str) -> dict:
    """Return preview md."""
    md = tmp_path / "doc.md"
    md.write_text(content, encoding="utf-8")
    budget = _section_tree_budget()
    handler = MarkdownFileHandler()
    params = {
        "file_path": str(md),
        "project_id": "test-proj",
        "node_ref": node_ref,
        "selector": None,
        "preview_budget": budget,
    }
    from code_analysis.commands.universal_file_preview.errors import PreviewError

    nav = navigate(handler, params, budget)
    assert not isinstance(nav, PreviewError)
    return build_envelope(nav, None, "none")


def _mock_db_bundle(tmp: Path) -> MagicMock:
    """Return mock db bundle."""
    db = MagicMock()
    row = {
        "id": _PROJECT_UUID,
        "root_path": str(tmp.resolve()),
        "watch_dir_id": None,
        "name": "test-project",
    }
    db.select.return_value = [row]
    proj = MagicMock()
    proj.root_path = str(tmp.resolve())
    db.get_project.return_value = proj
    return db


def _ensure_project_root(tmp: Path) -> None:
    """Return ensure project root."""
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            f'{{"id": "{_PROJECT_UUID}"}}\n',
            encoding="utf-8",
        )


async def _open_md(tmp: Path, rel: str, content: str) -> tuple[str, Path]:
    """Return open md."""
    _ensure_project_root(tmp)
    target = tmp / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    cmd = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_mock_db_bundle(tmp)
    ):
        res = await cmd.execute(
            **cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(res, SuccessResult)
    return str(res.data["session_id"]), target


def test_preview_md_section_includes_line_range_attributes(tmp_path: Path) -> None:
    """Verify test preview md section includes line range attributes."""
    envelope = _preview_md(tmp_path, _LEAF_SECTION, "only-section")
    attrs = envelope["focus"]["attributes"]
    assert attrs["start_line"] == "1"
    assert int(attrs["end_line"]) >= 3


@pytest.mark.asyncio
async def test_edit_md_replace_by_uuid_node_ref_from_annotated_preview(
    tmp_path: Path,
) -> None:
    """uuid5 block node_ref from annotated full-text preview must work in edit."""
    rel = "notes/uuid_doc.md"
    content = "# Title\n\nParagraph to replace.\n"
    sid, target = await _open_md(tmp_path, rel, content)
    path = str(target.resolve())
    token = next(
        t
        for t in MarkdownIt().parse(content)
        if t.type == "paragraph_open" and t.map is not None
    )
    block_ref = md_block_node_ref(path, token)

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "node_ref": block_ref,
                            "content": "Replaced paragraph.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
        await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
    text = target.read_text(encoding="utf-8")
    assert "Replaced paragraph." in text
    assert "Paragraph to replace." not in text


@pytest.mark.asyncio
async def test_edit_md_replace_by_node_ref(tmp_path: Path) -> None:
    """Verify test edit md replace by node ref."""
    rel = "notes/doc.md"
    sid, target = await _open_md(tmp_path, rel, _LEAF_SECTION)

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "node_ref": "only-section",
                            "content": "# Only Section\n\nReplaced body.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
        commit = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
    assert isinstance(commit, SuccessResult)
    text = target.read_text(encoding="utf-8")
    assert "Replaced body." in text
    assert "body text but no sub-sections" not in text


@pytest.mark.asyncio
async def test_edit_md_insert_by_node_ref_before_section(tmp_path: Path) -> None:
    """Verify test edit md insert by node ref before section."""
    rel = "notes/before.md"
    sid, target = await _open_md(tmp_path, rel, _LEAF_SECTION)

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": "only-section",
                            "position": "before",
                            "content": "## Preamble\n\nInserted before heading.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
        await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
    text = target.read_text(encoding="utf-8")
    assert text.index("## Preamble") < text.index("# Only Section")
    assert "Inserted before heading." in text


@pytest.mark.asyncio
async def test_edit_md_insert_position_after_colon_node_ref(tmp_path: Path) -> None:
    """Verify test edit md insert position after colon node ref."""
    rel = "notes/colon.md"
    sid, target = await _open_md(tmp_path, rel, _LEAF_SECTION)

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "position": "after:only-section",
                            "content": "## Trail\n\nAfter via colon syntax.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
        await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
    text = target.read_text(encoding="utf-8")
    assert "After via colon syntax." in text
    assert text.index("body text") < text.index("## Trail")


@pytest.mark.asyncio
async def test_edit_md_insert_by_node_ref_after_section(tmp_path: Path) -> None:
    """Verify test edit md insert by node ref after section."""
    rel = "notes/doc.md"
    sid, target = await _open_md(tmp_path, rel, _LEAF_SECTION)

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": "only-section",
                            "content": "## Added\n\nNew block.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
        await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
    text = target.read_text(encoding="utf-8")
    assert "New block." in text
    assert text.index("body text") < text.index("## Added")


@pytest.mark.asyncio
async def test_universal_file_read_line_slice(tmp_path: Path) -> None:
    """Verify test universal file read line slice."""
    _ensure_project_root(tmp_path)
    md = tmp_path / "readme.md"
    md.write_text("a\nb\nc\nd\n", encoding="utf-8")
    cmd = UniversalFileReadCommand()
    with (
        patch.object(
            BaseMCPCommand,
            "_open_database_from_config",
            return_value=_mock_db_bundle(tmp_path),
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=md,
        ),
    ):
        res = await cmd.execute(
            **cmd.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "file_path": "readme.md",
                    "start_line": 2,
                    "end_line": 3,
                }
            )
        )
    assert isinstance(res, SuccessResult)
    assert res.data["lines"] == ["b", "c"]
    assert res.data["start_line"] == 2
    assert res.data["end_line"] == 3


_MD_MULTI_BLOCK = """\
# HRS Title

First paragraph with {abc1}.

Second paragraph with {def2}.

Third paragraph with {ghi3}.
"""


@pytest.mark.asyncio
async def test_edit_md_insert_by_target_node_id_short_id(tmp_path: Path) -> None:
    """Marked-tree short_id via target_node_id must not fall back to line 1."""
    rel = "plans/source_spec.md"
    sid, target = await _open_md(tmp_path, rel, _MD_MULTI_BLOCK)

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": "4",
                            "position": "before",
                            "content": "Inserted between second and third.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
        await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
    text = target.read_text(encoding="utf-8")
    assert "Inserted between second and third." in text
    assert text.index("Second paragraph") < text.index(
        "Inserted between second and third."
    )
    assert text.index("Inserted between second and third.") < text.index(
        "Third paragraph"
    )
    assert not text.lstrip().startswith("Inserted between")


@pytest.mark.asyncio
async def test_edit_md_insert_by_node_ref_short_id(tmp_path: Path) -> None:
    """Integer node_ref from marked-tree preview inserts relative to that block."""
    rel = "plans/by_ref.md"
    sid, target = await _open_md(tmp_path, rel, _MD_MULTI_BLOCK)

    edit = UniversalFileEditCommand()
    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": "4",
                            "position": "before",
                            "content": "Via node_ref short_id.\n",
                        }
                    ],
                }
            )
        )
        assert isinstance(res, SuccessResult)
        await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
    text = target.read_text(encoding="utf-8")
    assert "Via node_ref short_id." in text
    assert text.index("Second paragraph") < text.index("Via node_ref short_id.")
    assert text.index("Via node_ref short_id.") < text.index("Third paragraph")


@pytest.mark.asyncio
async def test_edit_md_insert_unknown_slug_returns_error(tmp_path: Path) -> None:
    """Non-resolving slug node_ref must not silently insert at file head."""
    rel = "plans/bad_slug.md"
    sid, _target = await _open_md(tmp_path, rel, _MD_MULTI_BLOCK)

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": "no-such-section-slug",
                            "position": "before",
                            "content": "Should not appear.\n",
                        }
                    ],
                }
            )
        )
    assert isinstance(res, ErrorResult)
    assert res.code == "UNKNOWN_NODE_REF"


def test_preview_parent_section_line_range_through_subsections(tmp_path: Path) -> None:
    """# Parent spans until the next h1 (here: end of file), not only direct body lines."""
    envelope = _preview_md(tmp_path, _PARENT_WITH_SUBS, "parent")
    attrs = envelope["focus"]["attributes"]
    assert attrs["start_line"] == "1"
    assert int(attrs["end_line"]) == len(_PARENT_WITH_SUBS.splitlines())
