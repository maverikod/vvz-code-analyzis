"""
Undo/redo for universal_file_edit sessions across supported formats.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Callable, Iterator
from unittest.mock import MagicMock, patch

import pytest
import yaml
from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.edit_command import (
    UniversalFileEditCommand,
)
from code_analysis.commands.universal_file_edit.errors import (
    NOTHING_TO_REDO,
    NOTHING_TO_UNDO,
)
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.commands.universal_file_edit.session import get_session
from code_analysis.commands.universal_file_edit.session_redo_command import (
    SessionRedoCommand,
)
from code_analysis.commands.universal_file_edit.session_undo_command import (
    SessionUndoCommand,
)
from code_analysis.core.edit_session.edit_session import EditSession
from code_analysis.core.edit_session.session_history import SessionHistory
from code_analysis.core.tree_lifecycle.builder import TreeBuilder
from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum
from code_analysis.tree.contracts import NodeId
from code_analysis.tree.edit_operations import EditOperation, EditOperationKind
from code_analysis.tree.handler_registry import HandlerRegistry

_PROJECT_UUID = "00000000-0000-4000-8000-000000000099"


def _ensure_project_root(tmp: Path) -> None:
    """Return ensure project root."""
    marker = tmp / "projectid"
    if not marker.exists():
        marker.write_text('{"id": "00000000-0000-0000-0000-000000000001"}\n')


def _db(tmp: Path) -> MagicMock:
    """Return db."""
    bundle = MagicMock()
    proj = MagicMock()
    proj.root_path = str(tmp.resolve())
    proj.watch_dir_id = "watch-1"
    proj.name = "testproj"
    bundle.get_project.return_value = proj
    bundle.select.return_value = [
        {
            "root_path": str(tmp.resolve()),
            "watch_dir_id": "watch-1",
            "name": "testproj",
        }
    ]
    bundle.disconnect = MagicMock()
    return bundle


@contextmanager
def _mcp_project(tmp: Path) -> Iterator[MagicMock]:
    """Return mcp project."""
    db = _db(tmp)
    with patch.object(BaseMCPCommand, "_open_database_from_config", return_value=db):
        with patch.object(
            BaseMCPCommand,
            "_resolve_file_path_from_project",
            lambda _db, _pid, rel, require_exists=True: (tmp / rel).resolve(),
        ):
            with patch.object(
                BaseMCPCommand,
                "_resolve_project_root",
                lambda _pid: tmp.resolve(),
            ):
                with patch.object(
                    UniversalFileOpenCommand,
                    "_create_initial_backup",
                    lambda *_args, **_kwargs: None,
                ):
                    with patch(
                        "code_analysis.core.backup_manager.BackupManager.create_backup",
                        lambda *a, **k: None,
                    ):
                        yield db


def _build_tree(tmp: Path, rel: str, content: str) -> None:
    """Return build tree."""
    source = tmp / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    TreeBuilder.build(
        content=content,
        source_abs=source,
        file_path=rel,
        content_checksum=compute_content_checksum(content),
    )


def _json_scalar_short_id(source: Path, rel: str, field: str) -> int:
    """Return json scalar short id."""
    handler = HandlerRegistry.default_registry().resolve(source)
    nodes = handler.parse_content(Path(rel), source.read_text(encoding="utf-8"))
    ptr = f"/{field}"
    for node in nodes:
        if node.attributes.get("json_pointer") == ptr:
            return int(node.short_id)
    raise AssertionError(f"missing short_id for {ptr}")


def _python_function_stable_id(session_id: str, *, name: str = "value") -> str:
    """Return python function stable id."""
    from code_analysis.core.cst_tree.tree_builder import get_tree

    session = get_session(session_id)
    if not session.tree_id:
        raise AssertionError("sidecar session missing tree_id")
    tree = get_tree(session.tree_id)
    if tree is None:
        raise AssertionError("CST tree not loaded for session")
    for meta in tree.metadata_map.values():
        if meta.type == "FunctionDef" and meta.name == name:
            return meta.stable_id
    raise AssertionError(f"FunctionDef {name!r} not found in CST metadata")


def _python_stable_uuid(source: Path, rel: str) -> str:
    """Return python stable uuid."""
    from code_analysis.core.tree_lifecycle.node_id_map import parse_tree_file
    from code_analysis.tree.sibling_convention import sibling_tree_path

    sections = parse_tree_file(
        sibling_tree_path(source.resolve()).read_text(encoding="utf-8")
    )
    for entry in sections.map.entries:
        if entry.kind == "function" and entry.short_id == 1:
            return entry.uuid
    raise AssertionError("function stable uuid not found in session tree map")


def test_session_history_truncates_redo_branch() -> None:
    """Verify test session history truncates redo branch."""
    history = SessionHistory()
    history.reset("a" * 40)
    history.record("b" * 40)
    history.record("c" * 40)
    assert history.can_redo() is False
    history.move_to(0)
    history.record("d" * 40)
    assert history.timeline == ["a" * 40, "d" * 40]
    assert history.can_redo() is False


def test_core_undo_redo_and_edit_truncates_redo(tmp_path: Path) -> None:
    """Verify test core undo redo and edit truncates redo."""
    rel = "state/counter.json"
    _build_tree(tmp_path, rel, '{"counter": 1}\n')
    session = EditSession.open(
        source_abs=tmp_path / rel,
        project_root=tmp_path,
        file_path=rel,
    )
    try:
        sid = NodeId(_json_scalar_short_id(tmp_path / rel, rel, "counter"))

        def replace_with(value: str) -> None:
            """Return replace with."""
            session.apply_tree_operation(
                EditOperation(
                    kind=EditOperationKind.REPLACE,
                    short_id=sid,
                    new_content=value,
                )
            )

        replace_with("2")
        replace_with("3")
        assert json.loads(session.session_source_path.read_text())["counter"] == 3
        session.undo()
        assert json.loads(session.session_source_path.read_text())["counter"] == 2
        session.redo()
        assert json.loads(session.session_source_path.read_text())["counter"] == 3
        session.undo()
        session.undo()
        assert json.loads(session.session_source_path.read_text())["counter"] == 1
        replace_with("99")
        assert json.loads(session.session_source_path.read_text())["counter"] == 99
        assert session.history.can_redo() is False
    finally:
        session.close()


async def _open(tmp: Path, rel: str) -> str:
    """Return open."""
    _ensure_project_root(tmp)
    cmd = UniversalFileOpenCommand()
    with _mcp_project(tmp):
        res = await cmd.execute(
            **cmd.validate_params({"project_id": _PROJECT_UUID, "file_path": rel})
        )
    assert isinstance(res, SuccessResult), getattr(res, "message", res)
    return str(res.data["session_id"])


async def _edit(tmp: Path, session_id: str, operations: list[dict[str, Any]]) -> None:
    """Return edit."""
    cmd = UniversalFileEditCommand()
    with _mcp_project(tmp):
        res = await cmd.execute(
            **cmd.validate_params(
                {
                    "project_id": _PROJECT_UUID,
                    "session_id": session_id,
                    "operations": operations,
                }
            )
        )
    assert isinstance(res, SuccessResult), res


async def _undo(tmp: Path, session_id: str) -> dict[str, Any]:
    """Return undo."""
    with _mcp_project(tmp):
        res = await SessionUndoCommand().execute(
            project_id=_PROJECT_UUID, session_id=session_id
        )
    assert isinstance(res, SuccessResult), res
    return dict(res.data)


async def _redo(tmp: Path, session_id: str) -> dict[str, Any]:
    """Return redo."""
    with _mcp_project(tmp):
        res = await SessionRedoCommand().execute(
            project_id=_PROJECT_UUID, session_id=session_id
        )
    assert isinstance(res, SuccessResult), res
    return dict(res.data)


def _draft_text(tmp: Path, rel: str, session_id: str) -> str:
    """Return draft text."""
    session = get_session(session_id)
    assert session.file_path.replace("\\", "/") == rel.replace("\\", "/")
    return session.core.session_source_path.read_text(encoding="utf-8")


async def _assert_undo_redo_flow(
    tmp_path: Path,
    rel: str,
    *,
    setup: Callable[[Path], None],
    edit_batches: list[list[dict[str, Any]]],
    read_value: Callable[[str], Any],
    values_after_edits: list[Any],
    branch_edit: list[dict[str, Any]],
    branch_expected: Any,
    resolve_edits: (
        Callable[
            [str],
            tuple[list[list[dict[str, Any]]], list[dict[str, Any]]],
        ]
        | None
    ) = None,
) -> None:
    """Return assert undo redo flow."""
    setup(tmp_path)
    session_id = await _open(tmp_path, rel)
    if resolve_edits is not None:
        edit_batches, branch_edit = resolve_edits(session_id)
    for batch in edit_batches:
        await _edit(tmp_path, session_id, batch)

    assert read_value(_draft_text(tmp_path, rel, session_id)) == values_after_edits[-1]

    await _undo(tmp_path, session_id)
    assert read_value(_draft_text(tmp_path, rel, session_id)) == values_after_edits[-2]

    await _undo(tmp_path, session_id)
    assert read_value(_draft_text(tmp_path, rel, session_id)) == values_after_edits[0]

    await _redo(tmp_path, session_id)
    assert read_value(_draft_text(tmp_path, rel, session_id)) == values_after_edits[-2]

    await _edit(tmp_path, session_id, branch_edit)
    assert read_value(_draft_text(tmp_path, rel, session_id)) == branch_expected

    with _mcp_project(tmp_path):
        redo_res = await SessionRedoCommand().execute(
            project_id=_PROJECT_UUID, session_id=session_id
        )
    assert isinstance(redo_res, ErrorResult)
    assert redo_res.code == NOTHING_TO_REDO

    with _mcp_project(tmp_path):
        while True:
            undo_res = await SessionUndoCommand().execute(
                project_id=_PROJECT_UUID, session_id=session_id
            )
            if isinstance(undo_res, ErrorResult):
                assert undo_res.code == NOTHING_TO_UNDO
                break


@pytest.mark.asyncio
async def test_session_undo_redo_json(tmp_path: Path) -> None:
    """Verify test session undo redo json."""
    rel = "formats/data.json"
    await _assert_undo_redo_flow(
        tmp_path,
        rel,
        setup=lambda tmp: _build_tree(tmp, rel, '{"value": 1}\n'),
        edit_batches=[
            [{"type": "replace", "json_pointer": "/value", "value": 2}],
            [{"type": "replace", "json_pointer": "/value", "value": 3}],
        ],
        read_value=lambda text: json.loads(text)["value"],
        values_after_edits=[1, 2, 3],
        branch_edit=[{"type": "replace", "json_pointer": "/value", "value": 99}],
        branch_expected=99,
    )


@pytest.mark.asyncio
async def test_session_undo_redo_yaml(tmp_path: Path) -> None:
    """Verify test session undo redo yaml."""
    rel = "formats/config.yml"
    await _assert_undo_redo_flow(
        tmp_path,
        rel,
        setup=lambda tmp: _build_tree(tmp, rel, "value: 1\n"),
        edit_batches=[
            [{"type": "replace", "json_pointer": "/value", "value": 2}],
            [{"type": "replace", "json_pointer": "/value", "value": 3}],
        ],
        read_value=lambda text: yaml.safe_load(text)["value"],
        values_after_edits=[1, 2, 3],
        branch_edit=[{"type": "replace", "json_pointer": "/value", "value": 99}],
        branch_expected=99,
    )


@pytest.mark.asyncio
async def test_session_undo_redo_text(tmp_path: Path) -> None:
    """Verify test session undo redo text."""
    rel = "formats/notes.txt"

    def setup(tmp: Path) -> None:
        """Return setup."""
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("alpha\nbeta\n", encoding="utf-8")

    await _assert_undo_redo_flow(
        tmp_path,
        rel,
        setup=setup,
        edit_batches=[
            [
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "ALPHA\n",
                }
            ],
            [
                {
                    "type": "replace",
                    "start_line": 1,
                    "end_line": 1,
                    "content": "ALPHA2\n",
                }
            ],
        ],
        read_value=lambda text: text.splitlines()[0],
        values_after_edits=["alpha", "ALPHA", "ALPHA2"],
        branch_edit=[
            {
                "type": "replace",
                "start_line": 1,
                "end_line": 1,
                "content": "FINAL\n",
            }
        ],
        branch_expected="FINAL",
    )


@pytest.mark.asyncio
async def test_session_undo_redo_markdown(tmp_path: Path) -> None:
    """Verify test session undo redo markdown."""
    rel = "formats/readme.md"

    def setup(tmp: Path) -> None:
        """Return setup."""
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Title\n\nBody one.\n", encoding="utf-8")

    await _assert_undo_redo_flow(
        tmp_path,
        rel,
        setup=setup,
        edit_batches=[
            [
                {
                    "type": "replace",
                    "start_line": 3,
                    "end_line": 3,
                    "content": "Body two.\n",
                }
            ],
            [
                {
                    "type": "replace",
                    "start_line": 3,
                    "end_line": 3,
                    "content": "Body three.\n",
                }
            ],
        ],
        read_value=lambda text: text.splitlines()[2],
        values_after_edits=["Body one.", "Body two.", "Body three."],
        branch_edit=[
            {
                "type": "replace",
                "start_line": 3,
                "end_line": 3,
                "content": "Body final.\n",
            }
        ],
        branch_expected="Body final.",
    )


@pytest.mark.asyncio
async def test_session_undo_redo_python(tmp_path: Path) -> None:
    """Verify test session undo redo python."""
    rel = "formats/module.py"
    _build_tree(tmp_path, rel, "def value():\n    return 1\n")

    def read_return(text: str) -> int:
        """Return read return."""
        match = re.search(r"return\s+(\d+)", text)
        assert match is not None
        return int(match.group(1))

    def resolve_edits(
        session_id: str,
    ) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
        """Return resolve edits."""
        fn_stable = _python_function_stable_id(session_id)

        def replace(n: int) -> dict[str, Any]:
            """Return replace."""
            return {
                "type": "replace",
                "node_id": fn_stable,
                "code_lines": ["def value():", f"    return {n}"],
            }

        return (
            [[replace(2)], [replace(3)]],
            [replace(99)],
        )

    await _assert_undo_redo_flow(
        tmp_path,
        rel,
        setup=lambda tmp: None,
        edit_batches=[],
        read_value=read_return,
        values_after_edits=[1, 2, 3],
        branch_edit=[],
        branch_expected=99,
        resolve_edits=resolve_edits,
    )
