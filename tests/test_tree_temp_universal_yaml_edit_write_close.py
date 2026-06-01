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
from code_analysis.core.tree_lifecycle.node_id_map import parse_tree_file
from code_analysis.core.yaml_tree import tree_builder as ytb
from code_analysis.tree.sibling_convention import sibling_tree_path

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


def _sidecar(tmp: Path, rel: str = _REL) -> Path:
    return sibling_tree_path((tmp / rel).resolve())


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
    sections = parse_tree_file(sc.read_text(encoding="utf-8"))
    assert sections.checksums["source_sha256"] == _sha((tmp_path / _REL).read_bytes())
    assert sections.tree.strip() != ""
    assert sections.map.next_free >= 1


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


@pytest.mark.asyncio
async def test_yaml_replace_one_element_list_commits_as_sequence(
    tmp_path: Path,
) -> None:
    """Criterion A: replace with one-element list of dicts stays a YAML sequence."""
    rel = "records/single_seq.yml"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("source_ranges: []\n", encoding="utf-8")
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
                            "type": "replace",
                            "json_pointer": "/source_ranges",
                            "value": [{"start": 1336, "end": 1353}],
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
    text = p.read_text(encoding="utf-8")
    assert "\n- " in text or text.strip().startswith("- ")
    data = yaml.safe_load(text)
    assert isinstance(data["source_ranges"], list)
    assert data["source_ranges"] == [{"start": 1336, "end": 1353}]


@pytest.mark.asyncio
async def test_yaml_replace_one_element_scalar_list_commits_as_sequence(
    tmp_path: Path,
) -> None:
    """Criterion B: replace with one-element scalar list stays a sequence."""
    rel = "records/scalar_seq.yml"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("tags: []\n", encoding="utf-8")
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
                            "type": "replace",
                            "json_pointer": "/tags",
                            "value": ["x"],
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
    text = p.read_text(encoding="utf-8")
    assert "- x" in text or "- 'x'" in text or '- "x"' in text
    data = yaml.safe_load(text)
    assert isinstance(data["tags"], list)
    assert data["tags"] == ["x"]


@pytest.mark.asyncio
async def test_yaml_insert_one_element_list_into_mapping_commits_as_sequence(
    tmp_path: Path,
) -> None:
    """Criterion C: insert one-element list value under a mapping key."""
    rel = "records/insert_seq.yml"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("meta:\n  tag: old\n", encoding="utf-8")
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
                            "key": "items",
                            "value": [{"a": 1}],
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
    text = p.read_text(encoding="utf-8")
    assert "- a:" in text or "\n- " in text
    data = yaml.safe_load(text)
    assert isinstance(data["items"], list)
    assert data["items"] == [{"a": 1}]


@pytest.mark.asyncio
async def test_yaml_top_level_one_element_list_roundtrips_as_sequence(
    tmp_path: Path,
) -> None:
    """Criterion F: replacing a multi-item list with one item stays a YAML sequence."""
    rel = "records/top_level_seq.yml"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "source_ranges:\n  - start: 1\n    end: 2\n  - start: 3\n    end: 4\n",
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
                            "type": "replace",
                            "json_pointer": "/source_ranges",
                            "value": [{"start": 1336, "end": 1353}],
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
    text = p.read_text(encoding="utf-8")
    assert "\n- " in text
    data = yaml.safe_load(text)
    assert isinstance(data["source_ranges"], list)
    assert len(data["source_ranges"]) == 1
    assert data["source_ranges"][0] == {"start": 1336, "end": 1353}


@pytest.mark.asyncio
async def test_yaml_empty_list_and_dict_roundtrip(tmp_path: Path) -> None:
    """Criterion G: empty list and empty dict preserve container types."""
    rel = "records/empty_containers.yml"
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("items:\n  - id: 1\nslots: {}\n", encoding="utf-8")
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
                        {"type": "replace", "json_pointer": "/items", "value": []},
                        {"type": "replace", "json_pointer": "/slots", "value": {}},
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
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert isinstance(data["items"], list)
    assert data["items"] == []
    assert isinstance(data["slots"], dict)
    assert data["slots"] == {}
