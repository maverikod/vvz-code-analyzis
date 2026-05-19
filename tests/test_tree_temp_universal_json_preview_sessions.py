"""JSON tree-temp preview sessions and stable id behaviour (universal_file_preview).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.commands.universal_file_edit.write_command import (
    UniversalFileWriteCommand,
)
from code_analysis.commands.universal_file_preview import UniversalFilePreviewCommand
from code_analysis.core.json_tree import tree_builder as jtb

BLOCK_ID_KEY = "node_ref"
_PID = "baddbadd-badd-4badd-badd-baddbaddbadd"
_REL = "cfg/detail.json"
_DOC = '{"svc":{"env":"prod"},"tag":"go"}\n'


def _ensure_project_root(tmp: Path) -> None:
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            '{"id": "00000000-0000-0000-0000-000000000004"}\n',
            encoding="utf-8",
        )


def _db(tmp: Path) -> MagicMock:
    m = MagicMock()
    p = MagicMock()
    p.root_path = str(tmp.resolve())
    m.get_project.return_value = p
    return m


@pytest.fixture(autouse=True)
def _reset() -> None:
    jtb._trees.clear()
    yield
    jtb._trees.clear()


def _find_stable_by_path(payload: dict[str, Any], json_pointer: str) -> str:
    roots = cast(list[dict[str, Any]], payload["root"])
    if json_pointer in ("", "/"):
        assert len(roots) == 1
        return str(roots[0]["stable_id"])
    node: dict[str, Any] = roots[0]
    for raw in json_pointer.strip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if node.get("type") == "object":
            children = cast(list[dict[str, Any]], node.get("children") or [])
            match = next((c for c in children if c.get("key") == part), None)
            if match is None:
                raise KeyError(part)
            node = match
        elif node.get("type") == "array":
            children = cast(list[dict[str, Any]], node.get("children") or [])
            node = children[int(part)]
        else:
            raise AssertionError("cannot descend")
    return str(node["stable_id"])


def _ids(blocks: list[dict[str, Any]]) -> set[str]:
    return {str(b[BLOCK_ID_KEY]) for b in blocks}


async def _open_write_commit_close(tmp: Path, rel: str) -> None:
    op = UniversalFileOpenCommand()
    wr = UniversalFileWriteCommand()
    cl = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp)
    ):
        o = await op.execute(
            **op.validate_params({"project_id": _PID, "file_path": rel})
        )
        sid = str(o.data["session_id"])
        await wr.execute(
            **wr.validate_params(
                {"project_id": _PID, "session_id": sid, "write_mode": "preview"}
            )
        )
        await wr.execute(
            **wr.validate_params(
                {"project_id": _PID, "session_id": sid, "write_mode": "commit"}
            )
        )
        await cl.execute(**cl.validate_params({"project_id": _PID, "session_id": sid}))


async def _hydrate(tmp: Path) -> None:
    _ensure_project_root(tmp)
    p = tmp / _REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_DOC, encoding="utf-8")
    await _open_write_commit_close(tmp, _REL)


async def _preview(tmp: Path, node_ref: str | None) -> SuccessResult:
    cmd = UniversalFilePreviewCommand()
    raw: dict[str, Any] = {"project_id": _PID, "file_path": _REL}
    if node_ref is not None:
        raw["node_ref"] = node_ref
    params = cmd.validate_params(raw)
    res = await cmd.execute(**params)
    assert isinstance(res, SuccessResult)
    return res


@pytest.mark.asyncio
async def test_scalar_stable_id_resolves_container_children_matching_parent_preview(
    tmp_path: Path,
) -> None:
    await _hydrate(tmp_path)
    sc = tmp_path / ".trees" / f"{_REL}.tree"
    payload = json.loads(sc.read_text(encoding="utf-8"))
    svc_uuid = _find_stable_by_path(payload, "/svc")
    scalar_uuid = _find_stable_by_path(payload, "/svc/env")

    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        pr_par = await _preview(tmp_path, svc_uuid)
        pr_sc = await _preview(tmp_path, scalar_uuid)
    b1 = cast(list[dict[str, Any]], (pr_par.data or {}).get("blocks") or [])
    b2 = cast(list[dict[str, Any]], (pr_sc.data or {}).get("blocks") or [])
    p_set = _ids(b1)
    s_set = _ids(b2)
    assert p_set == s_set
    assert len(p_set) > 0


@pytest.mark.asyncio
async def test_root_scalar_json_preview_equivalent_without_ref(tmp_path: Path) -> None:
    _ensure_project_root(tmp_path)
    rel = "solo.json"
    p = tmp_path / rel
    p.write_text("false\n", encoding="utf-8")
    op = UniversalFileOpenCommand()
    cl = UniversalFileCloseCommand()
    wr = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        o = await op.execute(
            **op.validate_params({"project_id": _PID, "file_path": rel})
        )
        sid = str(o.data["session_id"])
        await wr.execute(
            **wr.validate_params(
                {"project_id": _PID, "session_id": sid, "write_mode": "preview"}
            )
        )
        await wr.execute(
            **wr.validate_params(
                {"project_id": _PID, "session_id": sid, "write_mode": "commit"}
            )
        )
        await cl.execute(**cl.validate_params({"project_id": _PID, "session_id": sid}))
    sc = tmp_path / ".trees" / f"{rel}.tree"
    payload = json.loads(sc.read_text(encoding="utf-8"))
    root_uuid = _find_stable_by_path(payload, "")
    cmd = UniversalFilePreviewCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        a = await cmd.execute(
            **cmd.validate_params({"project_id": _PID, "file_path": rel})
        )
        b = await cmd.execute(
            **cmd.validate_params(
                {"project_id": _PID, "file_path": rel, "node_ref": root_uuid}
            )
        )
    assert isinstance(a, SuccessResult) and isinstance(b, SuccessResult)
    fa = cast(dict[str, Any], a.data["focus"])
    fb = cast(dict[str, Any], b.data["focus"])
    assert fa.get("node_kind") == "scalar"
    assert fb.get("type") == "tree_sidecar_focus"
    assert isinstance(fb.get("node_ref"), str) and len(str(fb.get("node_ref"))) >= 32


@pytest.mark.asyncio
async def test_rescan_after_external_edit_and_removed_sidecar_generates_new_uuid(
    tmp_path: Path,
) -> None:
    await _hydrate(tmp_path)
    sc = tmp_path / ".trees" / f"{_REL}.tree"
    payload = json.loads(sc.read_text(encoding="utf-8"))
    old = _find_stable_by_path(payload, "/svc/env")
    (tmp_path / _REL).write_text(
        _DOC.replace("prod", "staging"),
        encoding="utf-8",
    )
    sc.unlink(missing_ok=True)
    await _open_write_commit_close(tmp_path, _REL)
    payload2 = json.loads(sc.read_text(encoding="utf-8"))
    new_u = _find_stable_by_path(payload2, "/svc/env")
    assert new_u != old


@pytest.mark.asyncio
async def test_stable_id_persists_across_sessions_without_disk_change(
    tmp_path: Path,
) -> None:
    await _hydrate(tmp_path)
    sc = tmp_path / ".trees" / f"{_REL}.tree"

    async def cycle() -> str:
        op = UniversalFileOpenCommand()
        cl = UniversalFileCloseCommand()
        with patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
        ):
            o = await op.execute(
                **op.validate_params({"project_id": _PID, "file_path": _REL})
            )
            sid = str(o.data["session_id"])
            await cl.execute(
                **cl.validate_params({"project_id": _PID, "session_id": sid})
            )
        payload = json.loads(sc.read_text(encoding="utf-8"))
        return _find_stable_by_path(payload, "/svc/env")

    u1 = await cycle()
    u2 = await cycle()
    u3 = await cycle()
    assert u1 == u2 == u3


@pytest.mark.asyncio
async def test_unknown_node_ref_errors(tmp_path: Path) -> None:
    await _hydrate(tmp_path)
    cmd = UniversalFilePreviewCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        res = await cmd.execute(
            **cmd.validate_params(
                {
                    "project_id": _PID,
                    "file_path": _REL,
                    "node_ref": "00000000-0000-4000-8000-00000000ffff",
                }
            )
        )
    assert isinstance(res, ErrorResult)
    assert res.code
    assert "UNKNOWN" in str(res.code).upper() or "INPUT" in str(res.code).upper()
