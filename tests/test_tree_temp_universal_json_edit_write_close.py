"""JSON tree-temp integration tests for universal_file_open/edit/write/close.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
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
from code_analysis.core.json_tree import tree_builder as jtb
from code_analysis.core.tree_lifecycle.node_id_map import parse_tree_file
from code_analysis.tree.sibling_convention import sibling_tree_path

_PROJECT_UUID = "cafebabe-cafe-4caf-babe-cafebabecafe"
_REL = "records/items.json"
_INIT = '{"items":[{"id":1,"active":false}],"meta":{"tag":"old"}}\n'


def _ensure_project_root(tmp: Path) -> None:
    """Return ensure project root."""
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            '{"id": "00000000-0000-0000-0000-000000000002"}\n',
            encoding="utf-8",
        )


def _db_for(tmp: Path) -> MagicMock:
    """Return db for."""
    m = MagicMock()
    p = MagicMock()
    p.root_path = str(tmp.resolve())
    m.get_project.return_value = p
    return m


def _clear() -> None:
    """Return clear."""
    jtb._trees.clear()


@pytest.fixture(autouse=True)
def _reset() -> None:
    """Return reset."""
    _clear()
    yield
    _clear()


def _sha(b: bytes) -> str:
    """Return sha."""
    return hashlib.sha256(b).hexdigest()


async def _prep(tmp: Path) -> str:
    """Return prep."""
    _ensure_project_root(tmp)
    p = tmp / _REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_INIT, encoding="utf-8")
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp)
    ):
        r = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": _REL})
        )
    assert isinstance(r, SuccessResult)
    return str(r.data["session_id"])


async def _two_phase_write(tmp: Path, sid: str) -> None:
    """Return two phase write."""
    wr = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp)
    ):
        p1 = await wr.execute(
            **wr.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
        p2 = await wr.execute(
            **wr.validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid, "write_mode": "commit"}
            )
        )
    assert isinstance(p1, SuccessResult) and p1.data.get("phase") == "preview"
    assert isinstance(p2, SuccessResult) and p2.data.get("phase") == "committed"


def _sidecar(tmp: Path, rel: str = _REL) -> Path:
    """Return sidecar."""
    return sibling_tree_path((tmp / rel).resolve())


@pytest.mark.asyncio
async def test_replace_via_json_pointer_updates_draft_then_commits(
    tmp_path: Path,
) -> None:
    """Verify test replace via json pointer updates draft then commits."""
    sid = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        er = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/items/0/active",
                            "value": True,
                        }
                    ],
                }
            )
        )
    assert isinstance(er, SuccessResult)
    await _two_phase_write(tmp_path, sid)
    cl = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await cl.execute(
            **cl.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )
    body = (tmp_path / _REL).read_text(encoding="utf-8")
    assert '"active": true' in body
    sc = _sidecar(tmp_path)
    assert sc.exists()
    sections = parse_tree_file(sc.read_text(encoding="utf-8"))
    assert sections.checksums["source_sha256"] == _sha((tmp_path / _REL).read_bytes())
    assert sections.tree.strip() != ""
    assert sections.map.next_free >= 1


@pytest.mark.asyncio
async def test_delete_scalar_property_meta_tag(tmp_path: Path) -> None:
    """Verify test delete scalar property meta tag."""
    sid = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [{"type": "delete", "json_pointer": "/meta/tag"}],
                }
            )
        )
    await _two_phase_write(tmp_path, sid)
    cl = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await cl.execute(
            **cl.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )
    data = json.loads((tmp_path / _REL).read_text(encoding="utf-8"))
    assert "tag" not in data.get("meta", {})


@pytest.mark.asyncio
async def test_insert_array_element_appends_via_append_semantics(
    tmp_path: Path,
) -> None:
    """Verify test insert array element appends via append semantics."""
    sid = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "/items",
                            "value": {"id": 2, "active": True},
                        }
                    ],
                }
            )
        )
    await _two_phase_write(tmp_path, sid)
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid}
            )
        )
    data = json.loads((tmp_path / _REL).read_text(encoding="utf-8"))
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_object_key_insert_relative_after_key_orders(tmp_path: Path) -> None:
    """Verify test object key insert relative after key orders."""
    rel = "records/ordered.json"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"first":1,"third":3}\n', encoding="utf-8")
    _ensure_project_root(tmp_path)
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        ores = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    sid = ores.data["session_id"]
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "",
                            "key": "second",
                            "value": 2,
                            "after_key": "first",
                        }
                    ],
                }
            )
        )
    await _two_phase_write(tmp_path, sid)
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid}
            )
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    assert list(data.keys()) == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_batch_abort_on_second_invalid_operation(tmp_path: Path) -> None:
    """Verify test batch abort on second invalid operation."""
    sid = await _prep(tmp_path)
    h0 = _sha((tmp_path / _REL).read_bytes())
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        out = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {"type": "delete", "json_pointer": "/not_there"},
                        {"type": "replace", "json_pointer": "/items/0/id", "value": 9},
                    ],
                }
            )
        )
    assert isinstance(out, ErrorResult)
    assert _sha((tmp_path / _REL).read_bytes()) == h0


@pytest.mark.asyncio
async def test_json_replace_one_element_list_stays_array(tmp_path: Path) -> None:
    """Criterion E: one-element JSON list must remain a JSON array after commit."""
    rel = "records/single_array.json"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"items":[]}\n', encoding="utf-8")
    _ensure_project_root(tmp_path)
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        ores = await op.execute(
            **op.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    sid = str(ores.data["session_id"])
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "replace",
                            "json_pointer": "/items",
                            "value": [{"a": 1}],
                        }
                    ],
                }
            )
        )
    await _two_phase_write(tmp_path, sid)
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db_for(tmp_path)
    ):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid}
            )
        )
    body = p.read_text(encoding="utf-8")
    assert '"items"' in body
    assert "[" in body
    data = json.loads(body)
    assert isinstance(data["items"], list)
    assert data["items"] == [{"a": 1}]
