"""YAML tree-temp integration for universal_file_open/edit/write/close.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
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
from code_analysis.core.tree_temp.sidecar_paths import resolve_trees_sidecar_path
from code_analysis.core.yaml_tree import tree_builder as ytb

_YAML_PROJECT_UUID = "d00dfeed-d00d-4d00-d00d-feedd00dfe1"
_REL = "records/stack.yml"
_BODY = """items:
  - id: 1
    active: false
meta:
  tag: old  # lbl
# eof
"""


def _ensure_project_root(tmp: Path) -> None:
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            '{"id": "00000000-0000-0000-0000-000000000003"}\n',
            encoding="utf-8",
        )


def _db(tmp: Path) -> MagicMock:
    m = MagicMock()
    p = MagicMock()
    p.root_path = str(tmp.resolve())
    m.get_project.return_value = p
    return m


def _clear() -> None:
    ytb._trees.clear()


@pytest.fixture(autouse=True)
def _reset() -> None:
    _clear()
    yield
    _clear()


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def _prep(tmp: Path) -> str:
    _ensure_project_root(tmp)
    p = tmp / _REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_BODY, encoding="utf-8")
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp)
    ):
        r = await op.execute(
            **op.validate_params({"project_id": _YAML_PROJECT_UUID, "file_path": _REL})
        )
    assert isinstance(r, SuccessResult)
    return str(r.data["session_id"])


async def _two_phase_write(tmp: Path, sid: str) -> None:
    wr = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp)
    ):
        p1 = await wr.execute(
            **wr.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
        p2 = await wr.execute(
            **wr.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
    assert isinstance(p1, SuccessResult) and p1.data.get("phase") == "preview"
    assert isinstance(p2, SuccessResult) and p2.data.get("phase") == "committed"


def _sidecar(tmp: Path) -> Path:
    return resolve_trees_sidecar_path(tmp.resolve(), Path(_REL))


@pytest.mark.asyncio
async def test_yaml_replace_via_json_pointer_updates_then_commits(
    tmp_path: Path,
) -> None:
    sid = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
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
    await _two_phase_write(tmp_path, sid)
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )
    data = yaml.safe_load((tmp_path / _REL).read_text(encoding="utf-8"))
    assert data["items"][0]["active"] is True
    sc = _sidecar(tmp_path)
    assert sc.exists()
    assert _sha((tmp_path / _REL).read_bytes())


@pytest.mark.asyncio
async def test_yaml_delete_meta_tag(tmp_path: Path) -> None:
    sid = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [{"type": "delete", "json_pointer": "/meta/tag"}],
                }
            )
        )
    await _two_phase_write(tmp_path, sid)
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )
    data = yaml.safe_load((tmp_path / _REL).read_text(encoding="utf-8"))
    assert "tag" not in data.get("meta", {})


@pytest.mark.asyncio
async def test_yaml_insert_array_appends(tmp_path: Path) -> None:
    sid = await _prep(tmp_path)
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
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
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )
    data = yaml.safe_load((tmp_path / _REL).read_text(encoding="utf-8"))
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_yaml_object_insert_after_key(tmp_path: Path) -> None:
    rel = "records/yorder.yml"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "first: 1\nthird: 3\n",
        encoding="utf-8",
    )
    _ensure_project_root(tmp_path)
    op = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        ores = await op.execute(
            **op.validate_params({"project_id": _YAML_PROJECT_UUID, "file_path": rel})
        )
    sid = str(ores.data["session_id"])
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
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
    wr = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await wr.execute(
            **wr.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
        await wr.execute(
            **wr.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "commit",
                }
            )
        )
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        await UniversalFileCloseCommand().execute(
            **UniversalFileCloseCommand().validate_params(
                {"project_id": _YAML_PROJECT_UUID, "session_id": sid}
            )
        )
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert list(data.keys()) == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_yaml_batch_invalid_first_operation(tmp_path: Path) -> None:
    sid = await _prep(tmp_path)
    h0 = _sha((tmp_path / _REL).read_bytes())
    ed = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        out = await ed.execute(
            **ed.validate_params(
                {
                    "project_id": _YAML_PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {"type": "delete", "json_pointer": "/nope"},
                        {"type": "replace", "json_pointer": "/items/0/id", "value": 9},
                    ],
                }
            )
        )
    assert isinstance(out, ErrorResult)
    assert _sha((tmp_path / _REL).read_bytes()) == h0
