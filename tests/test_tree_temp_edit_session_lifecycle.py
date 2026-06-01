"""EditSession and tree-temp sidecar disk lifecycle via universal_file_* commands.

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

_PROJECT_UUID = "baadf00d-baad-4bad-b00d-baaaaaaaaaaa"


def _ensure_project_root(tmp: Path) -> None:
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            '{"id": "00000000-0000-0000-0000-000000000001"}\n',
            encoding="utf-8",
        )


def _mock_db_bundle(tmp: Path) -> MagicMock:
    db = MagicMock()
    proj = MagicMock()
    proj.root_path = str(tmp.resolve())
    db.get_project.return_value = proj
    return db


def _sha_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clear_json_trees() -> None:
    jtb._trees.clear()


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    _clear_json_trees()
    yield
    _clear_json_trees()


async def _open(tmp: Path, rel: str = "nested/demo.json") -> tuple[str, Path]:
    _ensure_project_root(tmp)
    body = '{"counter":7}\n'
    target = tmp / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    cmd = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_mock_db_bundle(tmp)
    ):
        params = cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        res = await cmd.execute(**params)
    assert isinstance(res, SuccessResult)
    sid = res.data["session_id"]
    return sid, target


@pytest.mark.asyncio
async def test_roundtrip_commit_refreshes_sidecar_digest_matches_source(
    tmp_path: Path,
) -> None:
    rel = "nested/demo.json"
    sid, target = await _open(tmp_path, rel)
    initial_sha = _sha_hex(target.read_bytes())
    assert initial_sha

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        ep = edit.validate_params(
            {
                "project_id": _PROJECT_UUID,
                "session_id": sid,
                "operations": [
                    {"type": "replace", "json_pointer": "/counter", "value": 88},
                ],
            }
        )
        er = await edit.execute(**ep)
    assert isinstance(er, SuccessResult)

    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        r1 = await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
        r2 = await write.execute(
            **write.validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid, "write_mode": "commit"}
            )
        )
    assert isinstance(r1, SuccessResult)
    assert r1.data.get("phase") == "preview"
    assert isinstance(r2, SuccessResult)
    assert r2.data.get("phase") == "committed"
    assert "88" in target.read_text(encoding="utf-8")

    close = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        cr = await close.execute(
            **close.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )
    assert isinstance(cr, SuccessResult)

    final_sha = _sha_hex(target.read_bytes())
    source_path = (tmp_path / rel).resolve()
    sidecar_path = sibling_tree_path(source_path)
    assert sidecar_path.is_file()
    sections = parse_tree_file(sidecar_path.read_text(encoding="utf-8"))
    assert sections.checksums["source_sha256"] == final_sha


@pytest.mark.asyncio
async def test_close_without_write_after_edit_restores_original_hash(
    tmp_path: Path,
) -> None:
    rel = "nested/demo.json"
    sid, target = await _open(tmp_path, rel)
    snap = target.read_bytes()
    h0 = _sha_hex(snap)

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {"type": "replace", "json_pointer": "/counter", "value": 99}
                    ],
                }
            )
        )

    close = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        await close.execute(
            **close.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )

    assert target.read_bytes() == snap
    assert _sha_hex(target.read_bytes()) == h0


@pytest.mark.asyncio
async def test_insert_into_object_using_after_key_maintains_order(
    tmp_path: Path,
) -> None:
    rel = "nested/order.json"
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"alpha":true,"omega":false}\n', encoding="utf-8")
    _ensure_project_root(tmp_path)
    cmd = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await cmd.execute(
            **cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(res, SuccessResult)
    sid = res.data["session_id"]

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {
                            "type": "insert",
                            "parent_json_pointer": "",
                            "key": "between",
                            "value": 2,
                            "after_key": "alpha",
                        }
                    ],
                }
            )
        )

    write = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        await write.execute(
            **write.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "write_mode": "preview",
                }
            )
        )
        await write.execute(
            **write.validate_params(
                {"project_id": _PROJECT_UUID, "session_id": sid, "write_mode": "commit"}
            )
        )

    close = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        await close.execute(
            **close.validate_params({"project_id": _PROJECT_UUID, "session_id": sid})
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert list(data.keys()) == ["alpha", "between", "omega"]


@pytest.mark.asyncio
async def test_invalid_batch_returns_error_without_partial_mutation(
    tmp_path: Path,
) -> None:
    rel = "nested/batch.json"
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"a":1}\n', encoding="utf-8")
    _ensure_project_root(tmp_path)
    h0 = _sha_hex(path.read_bytes())
    cmd = UniversalFileOpenCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        res = await cmd.execute(
            **cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    sid = res.data["session_id"]

    edit = UniversalFileEditCommand()
    with patch.object(
        BaseMCPCommand,
        "_open_database_from_config",
        return_value=_mock_db_bundle(tmp_path),
    ):
        out = await edit.execute(
            **edit.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": sid,
                    "operations": [
                        {"type": "delete", "json_pointer": "/nope"},
                        {"type": "replace", "json_pointer": "/a", "value": 2},
                    ],
                }
            )
        )
    assert isinstance(out, ErrorResult)
    assert _sha_hex(path.read_bytes()) == h0
