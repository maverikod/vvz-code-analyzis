"""
In-process MCP regression tests for universal file commands and legacy text I/O.

Uses :meth:`mcp_proxy_adapter.commands.base.Command.run` (same entrypoint as MCP
Proxy) with ``tmp_path`` projects — no writes to ``vast_srv`` or real user trees.

Queue/proxy rule: assert top-level ``success`` and inner ``data.success`` (or
``error.code``) on every response dict from :meth:`~mcp_proxy_adapter.commands.result.CommandResult.to_dict`.
Live MCP Proxy checks (``list_servers``, ``call_server``) are manual when the
daemon is up; these tests mirror the same inner-envelope assertions via
``registry.get_command(...).run`` and :func:`assert_universal_success_envelope` /
:func:`assert_command_error_envelope`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

import code_analysis.hooks  # noqa: F401 — register_custom_commands_hook
from code_analysis.commands.base_mcp_command import BaseMCPCommand
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import hooks
from mcp_proxy_adapter.commands.result import SuccessResult

_PID = "550e8400-e29b-41d4-a716-446655440000"


def assert_command_error_envelope(d: Dict[str, Any], *, code: str) -> None:
    assert d.get("success") is False, d
    err = d.get("error") or {}
    assert err.get("code") == code, d


def assert_universal_success_envelope(d: Dict[str, Any]) -> None:
    assert d.get("success") is True, d
    inner = d.get("data") or {}
    assert inner.get("success") is True, d


def _persist_ok(**_: object) -> Dict[str, Any]:
    return {"success": True, "file_id": "stub-id", "metadata_only": True}


def _mock_db_for_root(tmp_path: Path) -> MagicMock:
    mock_db = MagicMock()
    mock_project = MagicMock()
    mock_project.root_path = str(tmp_path)
    mock_db.get_project.return_value = mock_project
    return mock_db


def _fake_run_ops_mode_python_apply(**kwargs: Any) -> SuccessResult:
    """Stub CST pipeline: apply=True writes predictable content (no real compose)."""
    root_path = kwargs["root_path"]
    file_path = kwargs["file_path"]
    target = (Path(root_path) / file_path).resolve()
    apply = bool(kwargs.get("apply", True))
    if apply:
        target.write_text("x = 99\n", encoding="utf-8")
    return SuccessResult(
        data={
            "success": True,
            "file_written": apply,
            "diff": bool(kwargs.get("return_diff")),
        }
    )


def _fake_json_save_apply_tree(**kwargs: Any) -> Dict[str, Any]:
    from code_analysis.core.json_tree.tree_builder import get_tree

    tree = get_tree(str(kwargs["tree_id"]))
    if not tree:
        return {
            "success": False,
            "error": "tree missing",
            "error_code": "VALIDATION_FAILED",
        }
    target = Path(kwargs["file_path"])
    target.write_text(
        json.dumps(tree.root_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"success": True, "file_path": str(target)}


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _register_commands() -> None:
    hooks.execute_custom_commands_hooks(registry)


@pytest.mark.asyncio
async def test_registry_exposes_universal_and_legacy_file_commands() -> None:
    for name in (
        "universal_file_read",
        "universal_file_save",
        "universal_file_replace",
        "universal_file_delete",
        "read_project_text_file",
        "write_project_text_lines",
        "create_text_file",
    ):
        assert registry.get_command(name) is not None, name


@pytest.mark.asyncio
async def test_mcp_md_universal_read_routes_text_handler(tmp_path: Path) -> None:
    doc = tmp_path / "page.md"
    doc.write_text("# H\n\nbody\n", encoding="utf-8")
    mock_db = _mock_db_for_root(tmp_path)
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=doc,
        ),
    ):
        r = await registry.get_command("universal_file_read").run(
            project_id=_PID,
            file_path="page.md",
        )
    d = r.to_dict()
    assert_universal_success_envelope(d)
    assert d["data"]["handler_id"] == "text"
    assert "# H" in "\n".join(d["data"].get("lines") or [])


@pytest.mark.asyncio
async def test_mcp_md_dry_run_diff_unchanged_then_apply_and_readback(
    tmp_path: Path,
) -> None:
    doc = tmp_path / "note.md"
    doc.write_text("alpha\nbeta\n", encoding="utf-8")
    mock_db = _mock_db_for_root(tmp_path)

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=doc,
        ),
        patch(
            "code_analysis.commands.universal_file_replace_command.persist_plain_text_file_metadata",
            side_effect=_persist_ok,
        ),
    ):
        dry = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="note.md",
            start_line=1,
            end_line=1,
            new_lines=["zed"],
            dry_run=True,
            diff=True,
        )
    dry_d = dry.to_dict()
    assert_universal_success_envelope(dry_d)
    assert dry_d["data"]["handler_id"] == "text"
    assert dry_d["data"]["dry_run"] is True
    assert "diff" in dry_d["data"]
    assert doc.read_text(encoding="utf-8") == "alpha\nbeta\n"

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=doc,
        ),
        patch(
            "code_analysis.commands.universal_file_replace_command.persist_plain_text_file_metadata",
            side_effect=_persist_ok,
        ),
    ):
        applied = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="note.md",
            start_line=1,
            end_line=1,
            new_lines=["zed"],
            dry_run=False,
            diff=False,
            backup=True,
        )
    app_d = applied.to_dict()
    assert_universal_success_envelope(app_d)
    assert doc.read_text(encoding="utf-8") == "zed\nbeta"

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=doc,
        ),
    ):
        rd = await registry.get_command("read_project_text_file").run(
            project_id=_PID,
            file_path="note.md",
            start_line=1,
            end_line=2,
        )
    legacy = rd.to_dict()
    assert legacy.get("success") is True
    assert legacy["data"].get("lines") == ["zed", "beta"]
    assert legacy["data"].get("handler_id") == "text"


@pytest.mark.asyncio
async def test_mcp_md_apply_replace_diff_true_inner_success_and_readback(
    tmp_path: Path,
) -> None:
    """Apply text replace with ``diff=true`` — inner ``data.success`` and readback."""
    doc = tmp_path / "live.md"
    doc.write_text("a\nb\nc\n", encoding="utf-8")
    mock_db = _mock_db_for_root(tmp_path)

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=doc,
        ),
        patch(
            "code_analysis.commands.universal_file_replace_command.persist_plain_text_file_metadata",
            side_effect=_persist_ok,
        ),
    ):
        applied = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="live.md",
            start_line=2,
            end_line=2,
            new_lines=["B"],
            dry_run=False,
            diff=True,
            backup=True,
        )
    app_d = applied.to_dict()
    assert_universal_success_envelope(app_d)
    assert app_d["data"]["handler_id"] == "text"
    assert "diff" in app_d["data"]
    assert doc.read_text(encoding="utf-8").splitlines() == ["a", "B", "c"]

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=doc,
        ),
    ):
        rd = await registry.get_command("universal_file_read").run(
            project_id=_PID,
            file_path="live.md",
        )
    assert_universal_success_envelope(rd.to_dict())
    assert rd.to_dict()["data"]["lines"] == ["a", "B", "c"]


@pytest.mark.asyncio
async def test_mcp_txt_universal_read_replace_routes_text_handler(
    tmp_path: Path,
) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("one\ntwo\n", encoding="utf-8")
    mock_db = _mock_db_for_root(tmp_path)

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=f,
        ),
    ):
        r = await registry.get_command("universal_file_read").run(
            project_id=_PID,
            file_path="notes.txt",
        )
    assert_universal_success_envelope(r.to_dict())
    assert r.to_dict()["data"]["handler_id"] == "text"

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=f,
        ),
        patch(
            "code_analysis.commands.universal_file_replace_command.persist_plain_text_file_metadata",
            side_effect=_persist_ok,
        ),
    ):
        rep = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="notes.txt",
            start_line=2,
            end_line=2,
            new_lines=["second"],
            dry_run=False,
            backup=True,
        )
    assert_universal_success_envelope(rep.to_dict())
    assert f.read_text(encoding="utf-8") == "one\nsecond"


@pytest.mark.parametrize(
    "name,body",
    (
        ("guide.rst", "Title\n-----\n"),
        ("book.adoc", "= Doc\n\n"),
    ),
)
@pytest.mark.asyncio
async def test_mcp_rst_adoc_universal_read_routes_text_handler(
    tmp_path: Path, name: str, body: str
) -> None:
    f = tmp_path / name
    f.write_text(body, encoding="utf-8")
    mock_db = _mock_db_for_root(tmp_path)
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=f,
        ),
    ):
        r = await registry.get_command("universal_file_read").run(
            project_id=_PID,
            file_path=name,
        )
    d = r.to_dict()
    assert_universal_success_envelope(d)
    assert d["data"]["handler_id"] == "text"


@pytest.mark.asyncio
async def test_mcp_json_read_replace_pointer_semantics_readback(tmp_path: Path) -> None:
    data_json = tmp_path / "cfg.json"
    data_json.write_text('{"a": 1, "b": 2}\n', encoding="utf-8")
    mock_db = _mock_db_for_root(tmp_path)

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=data_json,
        ),
    ):
        rd = await registry.get_command("universal_file_read").run(
            project_id=_PID,
            file_path="cfg.json",
        )
    read_d = rd.to_dict()
    assert_universal_success_envelope(read_d)
    assert read_d["data"]["handler_id"] == "json"
    assert "nodes" in read_d["data"]

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=data_json,
        ),
        patch(
            "code_analysis.core.file_handlers.json_handler.save_json_tree_to_file",
            side_effect=_fake_json_save_apply_tree,
        ),
    ):
        rep = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="cfg.json",
            operations=[{"action": "replace", "json_pointer": "/a", "value": 99}],
            dry_run=False,
            backup=False,
        )
    assert_universal_success_envelope(rep.to_dict())
    on_disk = json.loads(data_json.read_text(encoding="utf-8"))
    assert on_disk["a"] == 99
    assert on_disk["b"] == 2


@pytest.mark.asyncio
async def test_mcp_python_read_routes_python_handler(tmp_path: Path) -> None:
    py = tmp_path / "mod.py"
    py.write_text("x = 1\n", encoding="utf-8")
    mock_db = _mock_db_for_root(tmp_path)
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=py,
        ),
    ):
        r = await registry.get_command("universal_file_read").run(
            project_id=_PID,
            file_path="mod.py",
            start_line=1,
            end_line=1,
        )
    d = r.to_dict()
    assert_universal_success_envelope(d)
    assert d["data"]["handler_id"] == "python"


@pytest.mark.asyncio
async def test_mcp_python_replace_ops_cst_path_inner_success_readback(
    tmp_path: Path,
) -> None:
    """CST ``ops`` replace: inner success; disk updated (``run_ops_mode`` stubbed)."""
    root = tmp_path / "proj"
    root.mkdir()
    py = root / "mod.py"
    py.write_text("x = 1\n", encoding="utf-8")
    mock_db = MagicMock()
    mock_project = MagicMock()
    mock_project.root_path = str(root)
    mock_db.get_project.return_value = mock_project

    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=py,
        ),
        patch(
            "code_analysis.core.file_handlers.python_handler.run_ops_mode",
            side_effect=_fake_run_ops_mode_python_apply,
        ),
    ):
        r = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="mod.py",
            ops=[
                {
                    "selector": {"kind": "range", "start_line": 1, "end_line": 1},
                    "new_code": "x = 99\n",
                }
            ],
            dry_run=False,
            backup=True,
        )
    d = r.to_dict()
    assert_universal_success_envelope(d)
    assert d["data"]["handler_id"] == "python"
    assert py.read_text(encoding="utf-8") == "x = 99\n"


@pytest.mark.asyncio
async def test_mcp_python_replace_text_params_error_before_db(tmp_path: Path) -> None:
    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
        r = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="x.py",
            start_line=1,
            end_line=1,
            new_lines=["# n"],
        )
    odb.assert_not_called()
    assert_command_error_envelope(r.to_dict(), code="VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_mcp_unknown_extension_universal_read_before_db() -> None:
    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
        r = await registry.get_command("universal_file_read").run(
            project_id=_PID,
            file_path="data.unknownext_xyz",
        )
    odb.assert_not_called()
    assert_command_error_envelope(r.to_dict(), code="UNSUPPORTED_FILE_EXTENSION")


@pytest.mark.asyncio
async def test_mcp_toml_unsupported_read_and_replace_before_db() -> None:
    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
        r1 = await registry.get_command("universal_file_read").run(
            project_id=_PID,
            file_path="a.toml",
        )
    odb.assert_not_called()
    assert_command_error_envelope(r1.to_dict(), code="UNSUPPORTED_FILE_EXTENSION")

    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb2:
        r2 = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="a.toml",
            start_line=1,
            end_line=1,
            new_lines=["x"],
        )
    odb2.assert_not_called()
    assert_command_error_envelope(r2.to_dict(), code="UNSUPPORTED_FILE_EXTENSION")


@pytest.mark.asyncio
async def test_mcp_unknown_extension_unsupported_replace_before_db() -> None:
    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
        r = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="blob.unknownext_xyz",
            start_line=1,
            end_line=1,
            new_lines=["z"],
        )
    odb.assert_not_called()
    assert_command_error_envelope(r.to_dict(), code="UNSUPPORTED_FILE_EXTENSION")


@pytest.mark.asyncio
async def test_mcp_json_text_line_params_only_validation_error_before_db() -> None:
    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
        r = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="x.json",
            start_line=1,
            end_line=1,
            new_lines=['{"a": 1}'],
        )
    odb.assert_not_called()
    assert_command_error_envelope(r.to_dict(), code="VALIDATION_ERROR")


@pytest.mark.asyncio
async def test_mcp_text_replace_invalid_range_before_backup(
    tmp_path: Path,
) -> None:
    f = tmp_path / "t.txt"
    f.write_text("only\n", encoding="utf-8")
    mock_db = _mock_db_for_root(tmp_path)
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=f,
        ),
        patch(
            "code_analysis.commands.universal_file_replace_command.BackupManager",
        ) as bm_cls,
    ):
        r = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="t.txt",
            start_line=3,
            end_line=3,
            new_lines=["nope"],
        )
    bm_cls.assert_not_called()
    assert_command_error_envelope(r.to_dict(), code="INVALID_RANGE")
    assert f.read_text(encoding="utf-8") == "only\n"


@pytest.mark.asyncio
async def test_mcp_text_replace_overlapping_ranges_before_backup(
    tmp_path: Path,
) -> None:
    f = tmp_path / "t.txt"
    f.write_text("l1\nl2\nl3\n", encoding="utf-8")
    mock_db = _mock_db_for_root(tmp_path)
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=f,
        ),
        patch(
            "code_analysis.commands.universal_file_replace_command.BackupManager",
        ) as bm_cls,
    ):
        r = await registry.get_command("universal_file_replace").run(
            project_id=_PID,
            file_path="t.txt",
            replacements=[
                {"start_line": 1, "end_line": 1, "new_lines": ["a"]},
                {"start_line": 1, "end_line": 2, "new_lines": ["b"]},
            ],
        )
    bm_cls.assert_not_called()
    assert_command_error_envelope(r.to_dict(), code="INVALID_RANGE")
    assert f.read_text(encoding="utf-8") == "l1\nl2\nl3\n"


@pytest.mark.asyncio
async def test_mcp_write_project_text_lines_rejects_json_python_go_rs_codes() -> None:
    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
        rj = await registry.get_command("write_project_text_lines").run(
            project_id=_PID,
            file_path="d.json",
            start_line=1,
            end_line=1,
            new_lines=["{}"],
        )
    odb.assert_not_called()
    assert_command_error_envelope(rj.to_dict(), code="TEXT_FILE_SUFFIX_NOT_ALLOWED")

    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
        rp = await registry.get_command("write_project_text_lines").run(
            project_id=_PID,
            file_path="m.py",
            start_line=1,
            end_line=1,
            new_lines=["x"],
        )
    odb.assert_not_called()
    assert_command_error_envelope(rp.to_dict(), code="PYTHON_FILE_FORBIDDEN")

    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
        rg = await registry.get_command("write_project_text_lines").run(
            project_id=_PID,
            file_path="p.go",
            start_line=1,
            end_line=1,
            new_lines=["x"],
        )
    odb.assert_not_called()
    assert_command_error_envelope(rg.to_dict(), code="CODE_FILE_FORBIDDEN")

    with patch.object(BaseMCPCommand, "_open_database_from_config") as odb:
        rr = await registry.get_command("write_project_text_lines").run(
            project_id=_PID,
            file_path="l.rs",
            start_line=1,
            end_line=1,
            new_lines=["x"],
        )
    odb.assert_not_called()
    assert_command_error_envelope(rr.to_dict(), code="CODE_FILE_FORBIDDEN")


@pytest.mark.asyncio
async def test_mcp_create_text_file_md_via_registry(tmp_path: Path) -> None:
    target = tmp_path / "new.md"
    mock_db = _mock_db_for_root(tmp_path)
    with (
        patch.object(
            BaseMCPCommand, "_open_database_from_config", return_value=mock_db
        ),
        patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            return_value=target,
        ),
        patch(
            "code_analysis.commands.create_text_file_command.persist_plain_text_file_metadata",
            side_effect=_persist_ok,
        ),
    ):
        r = await registry.get_command("create_text_file").run(
            project_id=_PID,
            file_path="new.md",
            content="# Title\n",
        )
    d = r.to_dict()
    assert d.get("success") is True
    assert target.read_text(encoding="utf-8") == "# Title\n"
