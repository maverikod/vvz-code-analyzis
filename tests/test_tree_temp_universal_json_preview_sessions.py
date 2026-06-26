"""JSON tree-temp preview sessions and stable id behaviour (universal_file_preview).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

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
from code_analysis.commands.universal_file_edit.tree_temp_open_support import (
    TreeTempOpenAcquisition,
    acquire_tree_temp_for_open,
)
from code_analysis.core.json_tree import tree_builder as jtb
from code_analysis.core.tree_lifecycle.node_id_map import parse_tree_file
from code_analysis.core.tree_temp.tree_node import TreeNode
from code_analysis.tree.handler_registry import HandlerRegistry
from code_analysis.tree.sibling_convention import sibling_tree_path

BLOCK_ID_KEY = "node_ref"
_PID = "baddbadd-badd-4badd-badd-baddbaddbadd"
_REL = "cfg/detail.json"
_DOC = '{"svc":{"env":"prod"},"tag":"go"}\n'
_PREVIEW_ACQUIRE_PATCH = (
    "code_analysis.commands.universal_file_preview_command.acquire_tree_temp_for_open"
)


def _ensure_project_root(tmp: Path) -> None:
    """Return ensure project root."""
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            f'{{"id": "{_PID}"}}\n',
            encoding="utf-8",
        )


def _db(tmp: Path, project_id: str = _PID) -> MagicMock:
    """Return db."""
    m = MagicMock()
    m.select.return_value = [
        {
            "id": project_id,
            "root_path": str(tmp.resolve()),
            "watch_dir_id": None,
            "name": "test-project",
        }
    ]
    return m


@pytest.fixture(autouse=True)
def _reset() -> None:
    """Return reset."""
    jtb._trees.clear()
    yield
    jtb._trees.clear()


def _sidecar_path(tmp: Path, rel: str) -> Path:
    """Return sidecar path."""
    return sibling_tree_path((tmp / rel).resolve())


def _normalize_pointer(pointer: str) -> str:
    """Return normalize pointer."""
    if pointer in ("", "/"):
        return "/"
    return pointer if pointer.startswith("/") else f"/{pointer}"


def _short_id_for_pointer(*, source_path: Path, pointer: str) -> int:
    """Return short id for pointer."""
    handler = HandlerRegistry.default_registry().resolve(source_path)
    source_text = source_path.read_text(encoding="utf-8")
    nodes = handler.parse_content(source_path, source_text)
    want = _normalize_pointer(pointer)
    for node in nodes:
        jp = str(node.attributes.get("json_pointer", ""))
        if jp == want or (want == "/" and jp in ("", "/")):
            return int(node.short_id)
    raise KeyError(want)


def _uuid_for_pointer(*, source_path: Path, sidecar_path: Path, pointer: str) -> str:
    """Return uuid for pointer."""
    sections = parse_tree_file(sidecar_path.read_text(encoding="utf-8"))
    handler = HandlerRegistry.default_registry().resolve(source_path)
    source_text = source_path.read_text(encoding="utf-8")
    nodes = handler.parse_content(source_path, source_text)
    want = _normalize_pointer(pointer)
    target_short_id: int | None = None
    for node in nodes:
        jp = str(node.attributes.get("json_pointer", ""))
        if jp == want or (want == "/" and jp in ("", "/")):
            target_short_id = int(node.short_id)
            break
    if target_short_id is None:
        raise KeyError(want)
    for entry in sections.map.entries:
        if entry.short_id == target_short_id:
            return entry.uuid
    raise KeyError(want)


def _stable_id_in_forest(roots: list[TreeNode], pointer: str) -> str:
    """Return stable id in forest."""
    norm = _normalize_pointer(pointer)
    if norm == "/":
        assert len(roots) == 1
        return str(roots[0].stable_id)
    node = roots[0]
    for raw in norm.strip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if node.type == "object":
            children = node.children or []
            match = next((c for c in children if c.key == part), None)
            if match is None:
                raise KeyError(part)
            node = match
        elif node.type == "array":
            children = node.children or []
            node = children[int(part)]
        else:
            raise KeyError(pointer)
    return str(node.stable_id)


def _preview_acquisition(tmp: Path, rel: str) -> TreeTempOpenAcquisition:
    """Return preview acquisition."""
    source = (tmp / rel).resolve()
    return acquire_tree_temp_for_open(
        project_root=tmp.resolve(),
        source_abs=source,
        handler_id="json",
        raw_source_bytes=source.read_bytes(),
    )


def _ids(blocks: list[dict[str, Any]]) -> set[str]:
    """Return ids."""
    return {str(b[BLOCK_ID_KEY]) for b in blocks}


async def _open_write_commit_close(tmp: Path, rel: str) -> None:
    """Return open write commit close."""
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
    """Return hydrate."""
    _ensure_project_root(tmp)
    p = tmp / _REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_DOC, encoding="utf-8")
    await _open_write_commit_close(tmp, _REL)


async def _preview(tmp: Path, node_ref: str | int | None) -> SuccessResult:
    """Return preview."""
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
    """Verify test scalar stable id resolves container children matching parent preview."""
    await _hydrate(tmp_path)
    source = (tmp_path / _REL).resolve()
    svc_sid = _short_id_for_pointer(source_path=source, pointer="/svc")
    scalar_sid = _short_id_for_pointer(source_path=source, pointer="/svc/env")

    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        pr_par = await _preview(tmp_path, svc_sid)
        pr_sc = await _preview(tmp_path, scalar_sid)
    b1 = cast(list[dict[str, Any]], (pr_par.data or {}).get("blocks") or [])
    b2 = cast(list[dict[str, Any]], (pr_sc.data or {}).get("blocks") or [])
    p_set = _ids(b1)
    s_set = _ids(b2)
    assert p_set == s_set
    assert len(p_set) > 0


@pytest.mark.asyncio
async def test_root_scalar_json_preview_equivalent_without_ref(tmp_path: Path) -> None:
    """Verify test root scalar json preview equivalent without ref."""
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
    sc = _sidecar_path(tmp_path, rel)
    assert sc.is_file()
    root_sid = _short_id_for_pointer(source_path=p.resolve(), pointer="/")
    cmd = UniversalFilePreviewCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        a = await cmd.execute(
            **cmd.validate_params({"project_id": _PID, "file_path": rel})
        )
        b = await cmd.execute(
            **cmd.validate_params(
                {"project_id": _PID, "file_path": rel, "node_ref": root_sid}
            )
        )
    assert isinstance(a, SuccessResult) and isinstance(b, SuccessResult)
    fa = cast(dict[str, Any], a.data["focus"])
    fb = cast(dict[str, Any], b.data["focus"])
    assert fa.get("node_kind") == "scalar"
    assert isinstance(fb.get("node_ref"), int)
    assert fb.get("node_ref") == root_sid


@pytest.mark.asyncio
async def test_rescan_after_external_edit_and_removed_sidecar_generates_new_uuid(
    tmp_path: Path,
) -> None:
    """Verify test rescan after external edit and removed sidecar generates new uuid."""
    await _hydrate(tmp_path)
    sc = _sidecar_path(tmp_path, _REL)
    source = tmp_path / _REL
    old = _uuid_for_pointer(source_path=source, sidecar_path=sc, pointer="/svc/env")
    source.write_text(
        _DOC.replace("prod", "staging"),
        encoding="utf-8",
    )
    sc.unlink(missing_ok=True)
    await _open_write_commit_close(tmp_path, _REL)
    new_u = _uuid_for_pointer(source_path=source, sidecar_path=sc, pointer="/svc/env")
    assert new_u != old


@pytest.mark.asyncio
async def test_stable_id_persists_across_sessions_without_disk_change(
    tmp_path: Path,
) -> None:
    """Verify test stable id persists across sessions without disk change."""
    await _hydrate(tmp_path)
    sc = _sidecar_path(tmp_path, _REL)
    source = tmp_path / _REL

    async def cycle() -> str:
        """Return cycle."""
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
        return _uuid_for_pointer(
            source_path=source, sidecar_path=sc, pointer="/svc/env"
        )

    u1 = await cycle()
    u2 = await cycle()
    u3 = await cycle()
    assert u1 == u2 == u3


@pytest.mark.asyncio
async def test_unknown_node_ref_errors(tmp_path: Path) -> None:
    """Verify test unknown node ref errors."""
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
