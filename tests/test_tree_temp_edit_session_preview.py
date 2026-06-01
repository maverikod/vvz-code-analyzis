"""Tree-temp edit session preview must reflect draft state before commit.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import yaml
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from code_analysis.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from code_analysis.commands.universal_file_edit.format_group import (
    FORMAT_TREE_TEMP,
    FormatDescriptor,
    draft_path_for,
)
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.commands.universal_file_edit.session import (
    create_session,
    release_session,
)
from code_analysis.commands.universal_file_preview import UniversalFilePreviewCommand
from code_analysis.commands.universal_file_preview.session import (
    merge_edit_session_into_preview_params,
)
from code_analysis.core.tree_temp.tree_node import TreeNode
from code_analysis.core.yaml_tree import tree_builder as ytb

_YAML_PID = "a1a1a1a1-1111-4111-8111-111111111111"
_JSON_PID = "b2b2b2b2-2222-4222-8222-222222222222"
_YAML_REL = "plans/step.yaml"
_JSON_REL = "cfg/app.json"


def _ensure_project_root(tmp: Path) -> None:
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            '{"id": "00000000-0000-0000-0000-000000000001"}\n',
            encoding="utf-8",
        )


def _db(tmp: Path) -> MagicMock:
    m = MagicMock()
    p = MagicMock()
    p.root_path = str(tmp.resolve())
    m.get_project.return_value = p
    return m


@pytest.fixture(autouse=True)
def _reset_yaml_trees() -> None:
    ytb._trees.clear()
    yield
    ytb._trees.clear()


def test_merge_edit_session_injects_draft_path_for_tree_temp(tmp_path: Path) -> None:
    """FORMAT_TREE_TEMP sessions bind preview to draft_path, not stale disk source."""
    src = tmp_path / "cfg.yaml"
    src.write_text("a: 1\n", encoding="utf-8")
    descriptor = FormatDescriptor(
        format_group=FORMAT_TREE_TEMP,
        handler_id="yaml",
        draft_path=draft_path_for(src, FORMAT_TREE_TEMP),
        lockfile_path=src.with_suffix(src.suffix + ".write"),
        available_operations=["insert", "delete", "replace"],
    )
    edit_sess = create_session(
        abs_path=src,
        descriptor=descriptor,
        file_path="cfg.yaml",
        tree_id=None,
        tree_temp_roots=[
            TreeNode(stable_id="00000000-0000-4000-8000-000000000001", type="object")
        ],
    )
    try:
        merged = merge_edit_session_into_preview_params(
            {
                "project_id": "p",
                "file_path": "cfg.yaml",
                "session_id": edit_sess.session_id,
            }
        )
        assert merged["_preview_abs_path"] == str(edit_sess.draft_path)
        assert "tree_id" not in merged
    finally:
        release_session(edit_sess.session_id)


async def _open_yaml(tmp: Path) -> str:
    _ensure_project_root(tmp)
    p = tmp / _YAML_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "step_id: G-007\n"
        "name: session cleanup\n"
        "source_ranges:\n"
        "  - start: 97\n"
        "    end: 107\n",
        encoding="utf-8",
    )
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp)
    ):
        r = await op.execute(
            **op.validate_params({"project_id": _YAML_PID, "file_path": _YAML_REL})
        )
    assert isinstance(r, SuccessResult)
    return str(r.data["session_id"])


def _range_starts_from_blocks(data: dict[str, Any]) -> list[int]:
    blocks = cast(list[dict[str, Any]], data.get("blocks") or [])
    starts: list[int] = []
    for block in blocks:
        summary = cast(dict[str, Any], block.get("summary") or {})
        names = cast(list[str], summary.get("key_names") or [])
        values = cast(list[str], summary.get("key_values") or [])
        if "start" in names:
            idx = names.index("start")
            starts.append(int(values[idx]))
    return starts


def _preview_params(
    project_id: str,
    rel: str,
    session_id: str | None = None,
    node_ref: str | None = None,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "project_id": project_id,
        "file_path": rel,
        "full_text_max_lines": 0,
    }
    if session_id is not None:
        raw["session_id"] = session_id
    if node_ref is not None:
        raw["node_ref"] = node_ref
    return raw


@pytest.mark.asyncio
async def test_yaml_tree_temp_insert_visible_in_session_preview(
    tmp_path: Path,
) -> None:
    sid = await _open_yaml(tmp_path)
    ed = UniversalFileEditCommand()
    preview = UniversalFilePreviewCommand()
    close = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        edit_res = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "/source_ranges",
                            "index": 0,
                            "value": {"start": 5, "end": 7},
                        }
                    ],
                }
            )
        )
        assert isinstance(edit_res, SuccessResult)
        assert edit_res.data.get("updated") is True

        prev = await preview.execute(
            **preview.validate_params(
                _preview_params(_YAML_PID, _YAML_REL, sid, "/source_ranges")
            )
        )
        await close.execute(
            **close.validate_params({"project_id": _YAML_PID, "session_id": sid})
        )

    assert isinstance(prev, SuccessResult)
    assert cast(dict[str, Any], prev.data["focus"]).get("node_kind") == "sequence"
    assert _range_starts_from_blocks(cast(dict[str, Any], prev.data)) == [5, 97]


@pytest.mark.asyncio
async def test_yaml_tree_temp_replace_visible_in_session_preview(
    tmp_path: Path,
) -> None:
    sid = await _open_yaml(tmp_path)
    ed = UniversalFileEditCommand()
    preview = UniversalFilePreviewCommand()
    close = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        edit_res = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/source_ranges",
                            "value": [
                                {"start": 5, "end": 7},
                                {"start": 97, "end": 107},
                            ],
                        }
                    ],
                }
            )
        )
        assert isinstance(edit_res, SuccessResult)
        assert edit_res.data.get("updated") is True

        prev = await preview.execute(
            **preview.validate_params(
                _preview_params(_YAML_PID, _YAML_REL, sid, "/source_ranges")
            )
        )
        await close.execute(
            **close.validate_params({"project_id": _YAML_PID, "session_id": sid})
        )

    assert isinstance(prev, SuccessResult)
    assert cast(dict[str, Any], prev.data["focus"]).get("node_kind") == "sequence"
    assert _range_starts_from_blocks(cast(dict[str, Any], prev.data)) == [5, 97]


async def _open_json(tmp: Path) -> str:
    _ensure_project_root(tmp)
    p = tmp / _JSON_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"source_ranges": [{"start": 97, "end": 107}]}),
        encoding="utf-8",
    )
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp)
    ):
        r = await op.execute(
            **op.validate_params({"project_id": _JSON_PID, "file_path": _JSON_REL})
        )
    assert isinstance(r, SuccessResult)
    return str(r.data["session_id"])


async def _scalar_preview_value(
    tmp: Path,
    project_id: str,
    rel: str,
    session_id: str,
    node_ref: str,
) -> str:
    preview = UniversalFilePreviewCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp)
    ):
        res = await preview.execute(
            **preview.validate_params(
                _preview_params(project_id, rel, session_id, node_ref)
            )
        )
    assert isinstance(res, SuccessResult)
    focus = cast(dict[str, Any], res.data["focus"])
    return str(cast(dict[str, Any], focus.get("attributes") or {}).get("value"))


@pytest.mark.asyncio
async def test_json_tree_temp_preview_matches_draft(tmp_path: Path) -> None:
    sid = await _open_json(tmp_path)
    ed = UniversalFileEditCommand()
    preview = UniversalFilePreviewCommand()
    close = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _JSON_PID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "/source_ranges",
                            "index": 0,
                            "value": {"start": 5, "end": 7},
                        }
                    ],
                }
            )
        )
        prev_insert = await preview.execute(
            **preview.validate_params(
                _preview_params(_JSON_PID, _JSON_REL, sid, "/source_ranges")
            )
        )
        insert_first = await _scalar_preview_value(
            tmp_path, _JSON_PID, _JSON_REL, sid, "/source_ranges/0/start"
        )
        insert_second = await _scalar_preview_value(
            tmp_path, _JSON_PID, _JSON_REL, sid, "/source_ranges/1/start"
        )
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _JSON_PID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/source_ranges",
                            "value": [
                                {"start": 5, "end": 7},
                                {"start": 97, "end": 107},
                                {"start": 200, "end": 210},
                            ],
                        }
                    ],
                }
            )
        )
        prev_replace = await preview.execute(
            **preview.validate_params(
                _preview_params(_JSON_PID, _JSON_REL, sid, "/source_ranges")
            )
        )
        await close.execute(
            **close.validate_params({"project_id": _JSON_PID, "session_id": sid})
        )

    assert isinstance(prev_insert, SuccessResult)
    assert int(insert_first) == 5
    assert int(insert_second) == 97

    assert isinstance(prev_replace, SuccessResult)
    assert cast(dict[str, Any], prev_replace.data).get("total_blocks") == 3


@pytest.mark.asyncio
async def test_tree_temp_preview_without_commit_leaves_source_unchanged(
    tmp_path: Path,
) -> None:
    sid = await _open_yaml(tmp_path)
    source_path = tmp_path / _YAML_REL
    before = source_path.read_text(encoding="utf-8")
    ed = UniversalFileEditCommand()
    preview = UniversalFilePreviewCommand()
    close = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/name",
                            "value": "edited name",
                        }
                    ],
                }
            )
        )
        prev = await preview.execute(
            **preview.validate_params(
                _preview_params(_YAML_PID, _YAML_REL, sid, "/name")
            )
        )
        await close.execute(
            **close.validate_params({"project_id": _YAML_PID, "session_id": sid})
        )
        after_close = await preview.execute(
            **preview.validate_params(
                _preview_params(_YAML_PID, _YAML_REL, node_ref="/name")
            )
        )

    assert isinstance(prev, SuccessResult)
    edited = cast(dict[str, Any], prev.data["focus"])
    assert edited.get("attributes", {}).get("value") == "edited name"
    assert source_path.read_text(encoding="utf-8") == before
    assert isinstance(after_close, SuccessResult)
    reverted = cast(dict[str, Any], after_close.data["focus"])
    assert reverted.get("attributes", {}).get("value") == "session cleanup"
