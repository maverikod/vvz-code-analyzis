"""YAML tree-temp preview sessions (universal_file_preview).

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
from code_analysis.core.tree_lifecycle.node_id_map import parse_tree_file
from code_analysis.core.tree_temp.tree_node import TreeNode
from code_analysis.core.yaml_tree import tree_builder as ytb
from code_analysis.tree.handler_registry import HandlerRegistry
from code_analysis.tree.sibling_convention import sibling_tree_path

BLOCK_ID_KEY = "node_ref"
_PID_YAML = "1cedeced-1111-4222-8111-fedba5eba111"
_REL = "cluster/cfg/detail.yaml"
_BODY = """svc:
  env: prod
tag: go
# fin
"""
_PREVIEW_ACQUIRE_PATCH = (
    "code_analysis.commands.universal_file_preview_command.acquire_tree_temp_for_open"
)


def _ensure_project_root(tmp: Path) -> None:
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text(
            '{"id": "00000000-0000-0000-0000-000000000005"}\n',
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
    ytb._trees.clear()
    yield
    ytb._trees.clear()


def _sidecar_path(tmp: Path, rel: str) -> Path:
    return sibling_tree_path((tmp / rel).resolve())


def _normalize_pointer(pointer: str) -> str:
    if pointer in ("", "/"):
        return "/"
    return pointer if pointer.startswith("/") else f"/{pointer}"


def _pointer_to_key_path(pointer: str) -> str:
    norm = _normalize_pointer(pointer)
    if norm == "/":
        return ""
    return norm.strip("/").replace("/", ".")


def _uuid_for_pointer(*, source_path: Path, sidecar_path: Path, pointer: str) -> str:
    sections = parse_tree_file(sidecar_path.read_text(encoding="utf-8"))
    handler = HandlerRegistry.default_registry().resolve(source_path)
    source_text = source_path.read_text(encoding="utf-8")
    nodes = handler.parse_content(source_path, source_text)
    want = _pointer_to_key_path(pointer)
    target_short_id: int | None = None
    for node in nodes:
        kp = str(node.attributes.get("key_path", ""))
        if kp == want:
            target_short_id = int(node.short_id)
            break
    if target_short_id is None:
        raise KeyError(want)
    for entry in sections.map.entries:
        if entry.short_id == target_short_id:
            return entry.uuid
    raise KeyError(want)


def _stable_id_in_forest(roots: list[TreeNode], pointer: str) -> str:
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
    source = (tmp / rel).resolve()
    return acquire_tree_temp_for_open(
        project_root=tmp.resolve(),
        source_abs=source,
        handler_id="yaml",
        raw_source_bytes=source.read_bytes(),
    )


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
            **op.validate_params({"project_id": _PID_YAML, "file_path": rel})
        )
        sid = str(o.data["session_id"])
        await wr.execute(
            **wr.validate_params(
                {"project_id": _PID_YAML, "session_id": sid, "write_mode": "preview"}
            )
        )
        await wr.execute(
            **wr.validate_params(
                {"project_id": _PID_YAML, "session_id": sid, "write_mode": "commit"}
            )
        )
        await cl.execute(
            **cl.validate_params({"project_id": _PID_YAML, "session_id": sid})
        )


async def _hydrate(tmp: Path) -> None:
    _ensure_project_root(tmp)
    p = tmp / _REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_BODY, encoding="utf-8")
    await _open_write_commit_close(tmp, _REL)


async def _preview(tmp: Path, node_ref: str | None) -> SuccessResult:
    cmd = UniversalFilePreviewCommand()
    raw: dict[str, Any] = {"project_id": _PID_YAML, "file_path": _REL}
    if node_ref is not None:
        raw["node_ref"] = node_ref
    res = await cmd.execute(**cmd.validate_params(raw))
    assert isinstance(res, SuccessResult)
    return res


@pytest.mark.asyncio
async def test_yaml_scalar_node_ref_matches_container_preview_set(
    tmp_path: Path,
) -> None:
    await _hydrate(tmp_path)
    acq = _preview_acquisition(tmp_path, _REL)
    su = _stable_id_in_forest(acq.roots, "/svc")
    eu = _stable_id_in_forest(acq.roots, "/svc/env")
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
        ),
        patch(_PREVIEW_ACQUIRE_PATCH, return_value=acq),
    ):
        a = await _preview(tmp_path, su)
        b = await _preview(tmp_path, eu)
    assert _ids(cast(list[dict[str, Any]], a.data["blocks"])) == _ids(
        cast(list[dict[str, Any]], b.data["blocks"])
    )


@pytest.mark.asyncio
async def test_yaml_root_scalar_matches_absent_node_ref(tmp_path: Path) -> None:
    _ensure_project_root(tmp_path)
    rel = "solo.yaml"
    p = tmp_path / rel
    p.write_text("false\n", encoding="utf-8")
    op = UniversalFileOpenCommand()
    cl = UniversalFileCloseCommand()
    wr = UniversalFileWriteCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        o = await op.execute(
            **op.validate_params({"project_id": _PID_YAML, "file_path": rel})
        )
        sid = str(o.data["session_id"])
        await wr.execute(
            **wr.validate_params(
                {"project_id": _PID_YAML, "session_id": sid, "write_mode": "preview"}
            )
        )
        await wr.execute(
            **wr.validate_params(
                {"project_id": _PID_YAML, "session_id": sid, "write_mode": "commit"}
            )
        )
        await cl.execute(
            **cl.validate_params({"project_id": _PID_YAML, "session_id": sid})
        )
    sc = _sidecar_path(tmp_path, rel)
    assert sc.is_file()
    acq = _preview_acquisition(tmp_path, rel)
    rid = _stable_id_in_forest(acq.roots, "/")
    cmd = UniversalFilePreviewCommand()
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
        ),
        patch(_PREVIEW_ACQUIRE_PATCH, return_value=acq),
    ):
        x = await cmd.execute(
            **cmd.validate_params({"project_id": _PID_YAML, "file_path": rel})
        )
        y = await cmd.execute(
            **cmd.validate_params(
                {"project_id": _PID_YAML, "file_path": rel, "node_ref": rid}
            )
        )
    assert isinstance(x, SuccessResult) and isinstance(y, SuccessResult)
    fx = cast(dict[str, Any], x.data["focus"])
    fy = cast(dict[str, Any], y.data["focus"])
    assert fx.get("node_kind") == "scalar"
    assert fy.get("type") == "tree_sidecar_focus"
    assert isinstance(fy.get("node_ref"), str) and len(str(fy.get("node_ref"))) >= 32


@pytest.mark.asyncio
async def test_yaml_sidecar_regenerates_stable_id_after_external_edit_with_sidecar_removed(
    tmp_path: Path,
) -> None:
    await _hydrate(tmp_path)
    sc = _sidecar_path(tmp_path, _REL)
    source = tmp_path / _REL
    old = _uuid_for_pointer(source_path=source, sidecar_path=sc, pointer="/svc/env")
    source.write_text(
        _BODY.replace("prod", "staging"),
        encoding="utf-8",
    )
    sc.unlink(missing_ok=True)
    await _open_write_commit_close(tmp_path, _REL)
    assert (
        _uuid_for_pointer(source_path=source, sidecar_path=sc, pointer="/svc/env")
        != old
    )


@pytest.mark.asyncio
async def test_yaml_stable_id_stable_across_reopen_without_disk_change(
    tmp_path: Path,
) -> None:
    await _hydrate(tmp_path)
    sc = _sidecar_path(tmp_path, _REL)
    source = tmp_path / _REL

    async def grab() -> str:
        op = UniversalFileOpenCommand()
        cl = UniversalFileCloseCommand()
        with patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
        ):
            o = await op.execute(
                **op.validate_params({"project_id": _PID_YAML, "file_path": _REL})
            )
            sid = str(o.data["session_id"])
            await cl.execute(
                **cl.validate_params({"project_id": _PID_YAML, "session_id": sid})
            )
        return _uuid_for_pointer(
            source_path=source, sidecar_path=sc, pointer="/svc/env"
        )

    a = await grab()
    b = await grab()
    c = await grab()
    assert a == b == c


@pytest.mark.asyncio
async def test_yaml_unknown_node_ref_raises(tmp_path: Path) -> None:
    await _hydrate(tmp_path)
    cmd = UniversalFilePreviewCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=_db(tmp_path)
    ):
        res = await cmd.execute(
            **cmd.validate_params(
                {
                    "project_id": _PID_YAML,
                    "file_path": _REL,
                    "node_ref": "00000000-0000-4000-8000-00000000ffff",
                }
            )
        )
    assert isinstance(res, ErrorResult)
