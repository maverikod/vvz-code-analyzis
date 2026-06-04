"""
Preview node_ref must resolve consistently in universal_file_edit (all formats).

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
from code_analysis.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from code_analysis.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from code_analysis.commands.universal_file_preview import UniversalFilePreviewCommand
from code_analysis.core.json_tree import tree_builder as jtb

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"


def _db_for(tmp: Path, project_id: str = _PROJECT_UUID) -> MagicMock:
    db = MagicMock()
    row = {
        "id": project_id,
        "root_path": str(tmp.resolve()),
        "watch_dir_id": None,
        "name": "preview-edit-fmt-test",
    }
    db.select.return_value = [row]
    proj = MagicMock()
    proj.root_path = str(tmp.resolve())
    db.get_project.return_value = proj
    return db


def _ensure_project_root(tmp: Path) -> None:
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(json.dumps({"id": _PROJECT_UUID}) + "\n", encoding="utf-8")


async def _open_file(tmp: Path, rel: str, content: str) -> tuple[str, Path]:
    _ensure_project_root(tmp)
    target = tmp / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    cmd = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp)
    ):
        res = await cmd.execute(
            **cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    return str(res.data["session_id"]), target


async def _preview_blocks(
    tmp: Path, rel: str, *, session_id: str | None = None
) -> list[dict]:
    cmd = UniversalFilePreviewCommand()
    params: dict = {"project_id": _PROJECT_UUID, "file_path": rel}
    if session_id is not None:
        params["session_id"] = session_id
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp)
    ):
        res = await cmd.execute(**cmd.validate_params(params))
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    blocks = list((res.data or {}).get("blocks") or [])
    if blocks:
        return blocks
    if session_id is None:
        return blocks
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp)
    ):
        res = await cmd.execute(
            **cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    return list((res.data or {}).get("blocks") or [])


def _block_short_id(block: dict) -> str:
    ref = block.get("node_ref")
    if isinstance(ref, int):
        return str(ref)
    return str(ref).strip()


def _find_block_by_key_path(blocks: list[dict], key: str) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        attrs = str(summary.get("attribute_summary") or "")
        if f"key_path='{key}'" in attrs or f'key_path="{key}"' in attrs:
            return block
    raise AssertionError(f"no block for key {key!r} in {blocks!r}")


def _find_block_by_type(blocks: list[dict], node_type: str) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        if summary.get("type") == node_type:
            return block
    raise AssertionError(f"no block with type {node_type!r} in {blocks!r}")


def _find_block_by_json_pointer(blocks: list[dict], pointer: str) -> dict:
    for block in blocks:
        summary = block.get("summary") or {}
        attrs = str(summary.get("attribute_summary") or "")
        if f"json_pointer='{pointer}'" in attrs:
            return block
    raise AssertionError(f"no block for pointer {pointer!r} in {blocks!r}")


async def _commit(tmp: Path, sid: str, target: Path) -> str:
    write = UniversalFileWriteCommand()
    close = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp)
    ):
        await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
        await close.execute(
            **close.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )
    return target.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _reset_json_trees() -> None:
    jtb._trees.clear()
    yield
    jtb._trees.clear()


@pytest.mark.asyncio
async def test_json_insert_by_preview_short_id_target_node_id(
    tmp_path: Path,
) -> None:
    rel = "data/doc.json"
    body = '{"items": [{"id": 1}], "meta": {"tag": "old"}}\n'
    sid, target = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(tmp_path, rel, session_id=sid)
    meta_block = _find_block_by_json_pointer(blocks, "/meta")
    meta_sid = _block_short_id(meta_block)

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": meta_sid,
                            "position": "before",
                            "key": "note",
                            "value": "inserted",
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(tmp_path, sid, target)
    data = json.loads(text)
    keys = list(data.keys())
    assert keys.index("note") < keys.index("meta")
    assert data["note"] == "inserted"


@pytest.mark.asyncio
async def test_yaml_insert_by_preview_short_id_node_ref(tmp_path: Path) -> None:
    rel = "cfg/app.yaml"
    body = "alpha: 1\nbeta: 2\n"
    sid, target = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(tmp_path, rel, session_id=sid)
    beta_sid = _block_short_id(_find_block_by_key_path(blocks, "beta"))

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": beta_sid,
                            "position": "before",
                            "key": "middle",
                            "value": 99,
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(tmp_path, sid, target)
    assert text.index("middle:") < text.index("beta:")


@pytest.mark.asyncio
async def test_txt_insert_by_preview_short_id_target_node_id(
    tmp_path: Path,
) -> None:
    rel = "notes/readme.txt"
    body = "First paragraph line.\n\nSecond paragraph line.\n"
    sid, target = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(tmp_path, rel, session_id=sid)
    second_sid = _block_short_id(
        next(b for b in blocks if int(_block_short_id(b)) >= 2)
    )

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": second_sid,
                            "position": "before",
                            "content": "Inserted between paragraphs.\n",
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(tmp_path, sid, target)
    assert "Inserted between paragraphs." in text
    assert text.index("First paragraph") < text.index("Inserted between")
    assert text.index("Inserted between") < text.index("Second paragraph")


@pytest.mark.asyncio
async def test_jsonl_insert_by_preview_line_index_node_ref(tmp_path: Path) -> None:
    rel = "streams/events.jsonl"
    body = '{"event": "one"}\n{"event": "two"}\n'
    sid, target = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(tmp_path, rel, session_id=sid)
    line_ref = next(
        str(b["node_ref"]) for b in blocks if str(b.get("node_ref")) in ("1", 1)
    )

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "node_ref": line_ref,
                            "position": "before",
                            "content": '{"event": "middle"}\n',
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(tmp_path, sid, target)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert lines[1] == '{"event": "middle"}'


@pytest.mark.asyncio
async def test_py_insert_by_preview_short_id_target_node_id(tmp_path: Path) -> None:
    rel = "src/mod.py"
    body = '"""Module."""\n\nimport os\n\ndef foo() -> int:\n    return 1\n'
    sid, target = await _open_file(tmp_path, rel, body)
    blocks = await _preview_blocks(tmp_path, rel, session_id=sid)
    func_sid = _block_short_id(_find_block_by_type(blocks, "function"))

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": func_sid,
                            "position": "before",
                            "code_lines": [
                                "",
                                "def bar() -> int:",
                                "    return 2",
                            ],
                        }
                    ],
                }
            )
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    text = await _commit(tmp_path, sid, target)
    assert text.index("def bar") < text.index("def foo")


@pytest.mark.asyncio
async def test_json_unknown_node_ref_not_silent_success(tmp_path: Path) -> None:
    rel = "data/x.json"
    sid, _target = await _open_file(tmp_path, rel, '{"a": 1}\n')
    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        res = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "target_node_id": "99999",
                            "position": "before",
                            "key": "z",
                            "value": 0,
                        }
                    ],
                }
            )
        )
    assert isinstance(res, ErrorResult)
    assert res.code in ("UNKNOWN_NODE_REF", "INVALID_OPERATION")
