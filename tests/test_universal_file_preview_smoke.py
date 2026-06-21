"""
Smoke tests for universal_file_preview (no MCP; unit-level).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from mcp_proxy_adapter.commands.result import SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.read_only_batch_whitelist import READ_ONLY_BATCH_WHITELIST
from code_analysis.commands.universal_file_preview import UniversalFilePreviewCommand
from code_analysis.commands.universal_file_preview.budget import PreviewBudget
from code_analysis.commands.universal_file_preview.dispatcher import HandlerDispatcher
from code_analysis.commands.universal_file_preview.errors import (
    FILE_STRUCTURE_ERROR,
    INPUT_ERROR_CONFLICTING_PARAMETERS,
    INPUT_ERROR_UNKNOWN_EXTENSION,
    INPUT_ERROR_UNKNOWN_NODE_REF,
    PreviewError,
)
from code_analysis.commands.universal_file_preview.handlers.json_handler import (
    JsonFileHandler,
)
from code_analysis.commands.universal_file_preview.handlers.jsonl_handler import (
    JsonLinesFileHandler,
)
from code_analysis.commands.universal_file_preview.handlers.markdown_handler import (
    MarkdownFileHandler,
)
from code_analysis.commands.universal_file_preview.handlers.python_marked_handler import (
    PythonMarkedTreeHandler,
)
from code_analysis.commands.universal_file_preview.marked_tree_navigation import (
    navigate_marked_tree,
)
from code_analysis.core.search_session.tree_representation import TreeValidityState
from code_analysis.commands.universal_file_preview.handlers.text_handler import (
    TextFileHandler,
)
from code_analysis.commands.universal_file_preview.handlers.yaml_handler import (
    YamlFileHandler,
)
from code_analysis.commands.universal_file_preview.models import NodeKind
from code_analysis.commands.universal_file_preview.session import (
    merge_edit_session_into_preview_params,
    resolve_session,
)
from code_analysis.commands.universal_file_edit.open_command import (
    UniversalFileOpenCommand,
)
from code_analysis.commands.universal_file_edit.close_command import (
    UniversalFileCloseCommand,
)
from code_analysis.commands.universal_file_edit.session import (
    create_session,
    release_session,
)
from code_analysis.commands.universal_file_edit.format_group import (
    FormatDescriptor,
    FORMAT_SIDECAR,
)
from code_analysis.commands.cst_modify_tree_ops_build import build_tree_operations
from code_analysis.commands.universal_file_edit.sidecar_cst_apply import (
    _normalized_cst_modify_operation,
    _resolve_stable_to_span,
)
from code_analysis.core.cst_tree.tree_modifier import modify_tree
from code_analysis.core.cst_tree.tree_builder import load_file_to_tree, remove_tree
from code_analysis.core.json_tree.models import stable_node_id_for_pointer
from code_analysis.core.yaml_tree.tree_builder import (
    load_file_to_tree as load_yaml_file_to_tree,
    remove_tree as remove_yaml_tree,
)


_MD_PREVIEW_PID = "550e8400-e29b-41d4-a716-446655440001"
_MD_EMPTY_REF_PID = "550e8400-e29b-41d4-a716-446655440002"
_MD_DRAFT_PID = "550e8400-e29b-41d4-a716-446655440003"
_MD_CREATE_PID = "550e8400-e29b-41d4-a716-446655440004"


def _universal_preview_pkg_dir() -> pathlib.Path:
    return (
        pathlib.Path(__file__).resolve().parent.parent
        / "code_analysis"
        / "commands"
        / "universal_file_preview"
    )


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def _repo_project_id() -> str:
    raw = (_repo_root() / "projectid").read_text(encoding="utf-8")
    return str(json.loads(raw)["id"])


def _mock_db_for_root(root: pathlib.Path, project_id: str) -> MagicMock:
    mock_db = MagicMock()
    mock_db.select.return_value = [
        {
            "id": project_id,
            "root_path": str(root.resolve()),
            "watch_dir_id": None,
            "name": "test-project",
        }
    ]
    return mock_db


def test_command_name_and_schema_structure() -> None:
    """Command name and shallow schema layout for MCP integration."""
    assert UniversalFilePreviewCommand.name == "universal_file_preview"
    schema = UniversalFilePreviewCommand.get_schema()
    assert isinstance(schema, dict)
    assert schema.get("type") == "object"
    props = schema.get("properties")
    assert isinstance(props, dict)
    assert "project_id" in props
    assert "file_path" in props
    assert "session_id" in props


def test_merge_edit_session_injects_tree_id_for_sidecar(tmp_path) -> None:
    """Preview with session_id uses the edit session in-memory CST tree."""
    path = tmp_path / "mod.py"
    path.write_text(
        "def foo():\n    return 1\n\ndef bar():\n    return 2\n",
        encoding="utf-8",
    )
    tree = load_file_to_tree(str(path))
    try:
        foo_meta = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "foo"
        )
        bar_meta = next(
            m
            for m in tree.metadata_map.values()
            if m.type == "FunctionDef" and m.name == "bar"
        )
        op = {
            "type": "replace",
            "node_id": foo_meta.stable_id,
            "code_lines": ["def foo():\n", "    return 99\n"],
        }
        resolved = _resolve_stable_to_span(op, tree)
        built, err = build_tree_operations(
            tree, [_normalized_cst_modify_operation(resolved)]
        )
        assert err is None and built
        tree = modify_tree(tree.tree_id, built)

        descriptor = FormatDescriptor(
            format_group=FORMAT_SIDECAR,
            handler_id="python",
            draft_path=path.with_suffix(path.suffix + ".cst_sidecar"),
            lockfile_path=path.with_suffix(path.suffix + ".write"),
            available_operations=["replace"],
        )
        edit_sess = create_session(
            abs_path=path,
            descriptor=descriptor,
            file_path="mod.py",
            tree_id=tree.tree_id,
        )
        try:
            merged = merge_edit_session_into_preview_params(
                {
                    "project_id": "p",
                    "file_path": "mod.py",
                    "session_id": edit_sess.session_id,
                }
            )
            assert not isinstance(merged, PreviewError)
            assert merged["tree_id"] == tree.tree_id

            handler = PythonMarkedTreeHandler()
            session_result = resolve_session(handler, merged)
            assert not isinstance(session_result, PreviewError)
            session, origin, _ = session_result
            assert session is None
            assert origin == "none"
        finally:
            release_session(edit_sess.session_id)
    finally:
        remove_tree(tree.tree_id)


def test_merge_edit_session_unknown_session_id_returns_error() -> None:
    bogus = "00000000-0000-4000-8000-000000000099"
    out = merge_edit_session_into_preview_params(
        {"file_path": "a.py", "session_id": bogus}
    )
    assert isinstance(out, PreviewError)
    assert out.code == INPUT_ERROR_CONFLICTING_PARAMETERS


def test_handler_dispatcher_known_and_unknown_extensions() -> None:
    """Dispatch maps extensions to handlers; unknown extension is PreviewError."""
    d = HandlerDispatcher()
    py_h = d.dispatch("a.py")
    assert isinstance(py_h, PythonMarkedTreeHandler)
    md_h = d.dispatch("notes.md")
    assert isinstance(md_h, MarkdownFileHandler)
    json_h = d.dispatch("cfg.json")
    assert isinstance(json_h, JsonFileHandler)
    yaml_h = d.dispatch("cfg.yaml")
    assert isinstance(yaml_h, YamlFileHandler)
    jsonl_h = d.dispatch("data.jsonl")
    assert isinstance(jsonl_h, JsonLinesFileHandler)

    bad = d.dispatch("x.xml")
    assert isinstance(bad, PreviewError)
    assert bad.code == INPUT_ERROR_UNKNOWN_EXTENSION


def test_resolve_session_unknown_tree_id_returns_preview_error() -> None:
    """Unknown caller tree_id surfaces as input PreviewError (registry miss)."""
    handler = MagicMock()
    bogus = "00000000-0000-4000-8000-000000000099"
    out = resolve_session(handler, {"tree_id": bogus})
    assert isinstance(out, PreviewError)
    assert out.code == INPUT_ERROR_CONFLICTING_PARAMETERS


def test_resolve_session_md_ignores_stale_tree_id(tmp_path) -> None:
    """Markdown preview must not bind a CST tree session from a stale tree_id."""
    from code_analysis.core.cst_tree.tree_builder import load_file_to_tree

    py = tmp_path / "mod.py"
    py.write_text("x = 1\n", encoding="utf-8")
    tree = load_file_to_tree(str(py))
    out = resolve_session(MarkdownFileHandler(), {"tree_id": tree.tree_id})
    assert not isinstance(out, PreviewError)
    session, origin, tree_id = out
    assert session is None
    assert origin == "none"
    assert tree_id is None


def test_python_marked_tree_preview_valid_syntax(tmp_path) -> None:
    path = tmp_path / "t.py"
    path.write_text("x = 1\n", encoding="utf-8")
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=200
    )
    with patch(
        "code_analysis.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        result = navigate_marked_tree(
            {
                "project_root": tmp_path,
                "rel_file_path": "t.py",
                "file_path": str(path),
                "node_ref": None,
                "selector": None,
                "session_id": None,
            },
            budget,
        )
    assert not isinstance(result, PreviewError)
    assert result.short_id_refs is True
    assert result.selected_blocks


def test_python_marked_tree_class_methods_in_blocks(tmp_path) -> None:
    src = '''\
class Outer:
    def one(self) -> None:
        """doc1"""
        pass

    def two(self) -> None:
        """doc2"""
        pass
'''
    path = tmp_path / "mod.py"
    path.write_text(src, encoding="utf-8")
    budget = PreviewBudget(
        preview_lines=10, value_preview_len=80, full_text_max_lines=500
    )
    with patch(
        "code_analysis.commands.universal_file_preview.marked_tree_loader.TreeLifecycle.from_path",
        return_value=(MagicMock(), TreeValidityState.reused),
    ):
        result = navigate_marked_tree(
            {
                "project_root": tmp_path,
                "rel_file_path": "mod.py",
                "file_path": str(path),
                "node_ref": None,
                "selector": "0:10",
                "session_id": None,
            },
            budget,
        )
    assert not isinstance(result, PreviewError)
    texts = " ".join((b.text or "") for b in result.selected_blocks)
    assert "def one" in texts
    assert "def two" in texts


def test_text_handler_open_root_lines_kind(tmp_path) -> None:
    path = tmp_path / "t.md"
    path.write_text("single line\n", encoding="utf-8")
    result = TextFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.LINES


def test_json_handler_open_root_mapping_kind(tmp_path) -> None:
    path = tmp_path / "t.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    result = JsonFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.MAPPING


def test_json_handler_resolve_opaque_node_id_matches_list_json_blocks(tmp_path) -> None:
    """opaque node_id (uuid5 pointer) resolves like JSON Pointer."""
    path = tmp_path / "t.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    h = JsonFileHandler()
    opened = h.open_root(str(path), None)
    assert not isinstance(opened, PreviewError)
    root_id = stable_node_id_for_pointer("")
    key_id = stable_node_id_for_pointer("/a")
    by_root_id = h.resolve_node_ref(root_id, None)
    assert not isinstance(by_root_id, PreviewError)
    assert by_root_id.node_kind == NodeKind.MAPPING
    assert by_root_id.node_ref == ""
    by_key_id = h.resolve_node_ref(key_id, None)
    assert not isinstance(by_key_id, PreviewError)
    assert by_key_id.node_kind == NodeKind.SCALAR
    assert by_key_id.node_ref == "/a"
    bad = h.resolve_node_ref("not-a-known-json-node-id", None)
    assert isinstance(bad, PreviewError)
    assert bad.code == INPUT_ERROR_UNKNOWN_NODE_REF


def test_yaml_handler_resolve_opaque_node_id_matches_stable_pointer(tmp_path) -> None:
    """opaque node_id (uuid5 pointer) resolves like JSON Pointer for YAML."""
    pytest.importorskip("yaml")
    path = tmp_path / "t.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    h = YamlFileHandler()
    opened = h.open_root(str(path), None)
    assert not isinstance(opened, PreviewError)
    root_id = stable_node_id_for_pointer("")
    key_id = stable_node_id_for_pointer("/a")
    by_root_id = h.resolve_node_ref(root_id, None)
    assert not isinstance(by_root_id, PreviewError)
    assert by_root_id.node_kind == NodeKind.MAPPING
    assert by_root_id.node_ref == ""
    by_key_id = h.resolve_node_ref(key_id, None)
    assert not isinstance(by_key_id, PreviewError)
    assert by_key_id.node_kind == NodeKind.SCALAR
    assert by_key_id.node_ref == "/a"


def test_resolve_session_finds_yaml_tree_session(tmp_path) -> None:
    """Caller-owned tree_id may resolve to a registered YAML tree."""
    pytest.importorskip("yaml")
    path = tmp_path / "sess.yaml"
    path.write_text("k: v\n", encoding="utf-8")
    tree = load_yaml_file_to_tree(str(path))
    try:
        out = resolve_session(MagicMock(), {"tree_id": tree.tree_id})
        assert not isinstance(out, PreviewError)
        session, origin, _ = out
        assert origin == "caller_owned"
        assert session is tree
    finally:
        remove_yaml_tree(tree.tree_id)


def test_list_yaml_blocks_command_registered_name() -> None:
    from code_analysis.commands.list_yaml_blocks_command import ListYamlBlocksCommand

    assert ListYamlBlocksCommand.name == "list_yaml_blocks"


def test_yaml_handler_open_root_mapping_kind(tmp_path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "t.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    result = YamlFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.MAPPING


def test_yaml_handler_open_root_scalar_int(tmp_path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "scalar.yaml"
    path.write_text("42\n", encoding="utf-8")
    result = YamlFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.SCALAR
    assert result.attributes.get("value") == "42"


def test_yaml_handler_open_root_scalar_string(tmp_path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "scalar.yaml"
    path.write_text("hi\n", encoding="utf-8")
    result = YamlFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.SCALAR
    assert result.attributes.get("value") == "hi"


def test_yaml_handler_open_root_sequence(tmp_path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "seq.yaml"
    path.write_text("[1, 2]\n", encoding="utf-8")
    result = YamlFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.SEQUENCE


def test_yaml_handler_invalid_yaml_returns_invalid_source_node(tmp_path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "bad.yaml"
    path.write_text("key: [\n", encoding="utf-8")
    result = YamlFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.is_invalid is True
    assert result.node_ref == ""
    assert "key: [" in result.attributes.get("text", "")
    assert "parse_error" in result.attributes


def test_yaml_handler_resolve_node_ref_mapping_key(tmp_path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "map.yaml"
    path.write_text("key: 7\n", encoding="utf-8")
    h = YamlFileHandler()
    opened = h.open_root(str(path), None)
    assert not isinstance(opened, PreviewError)
    resolved = h.resolve_node_ref("/key", None)
    assert not isinstance(resolved, PreviewError)
    assert resolved.node_kind == NodeKind.SCALAR
    assert resolved.node_ref == "/key"
    assert resolved.attributes.get("value") == "7"


def test_yaml_handler_drill_down_small_mapping_annotated_full_text(
    tmp_path: pathlib.Path,
) -> None:
    pytest.importorskip("yaml")
    big_block = "\n".join(f"  filler_{i}: {i}" for i in range(30))
    path = tmp_path / "nested.yaml"
    path.write_text(
        f"big:\n{big_block}\nsmall:\n  a: 1\n  b: 2\n  c: 3\n  d: 4\n  e: 5\n",
        encoding="utf-8",
    )
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=120, full_text_max_lines=10
    )
    h = YamlFileHandler()
    root = h.open_root(str(path), None, budget=budget)
    assert not isinstance(root, PreviewError)
    assert root.node_kind == NodeKind.MAPPING
    resolved = h.resolve_node_ref("/small", None)
    assert not isinstance(resolved, PreviewError)
    assert resolved.attributes.get("full_text") is True
    text = resolved.attributes.get("text", "")
    assert "[/small/a]" in text
    assert "a: 1" in text
    assert "filler_0" not in text


def test_yaml_handler_drill_down_large_mapping_stays_structural(
    tmp_path: pathlib.Path,
) -> None:
    pytest.importorskip("yaml")
    big_block = "\n".join(f"  filler_{i}: {i}" for i in range(30))
    path = tmp_path / "nested.yaml"
    path.write_text(
        f"big:\n{big_block}\nsmall:\n  a: 1\n  b: 2\n  c: 3\n  d: 4\n  e: 5\n",
        encoding="utf-8",
    )
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=120, full_text_max_lines=3
    )
    h = YamlFileHandler()
    assert not isinstance(h.open_root(str(path), None, budget=budget), PreviewError)
    resolved = h.resolve_node_ref("/big", None)
    assert not isinstance(resolved, PreviewError)
    assert resolved.node_kind == NodeKind.MAPPING
    assert resolved.attributes.get("full_text") is not True


def test_json_handler_drill_down_small_mapping_annotated_full_text(
    tmp_path: pathlib.Path,
) -> None:
    big_lines = ",\n".join(f'    "filler_{i}": {i}' for i in range(30))
    path = tmp_path / "nested.json"
    path.write_text(
        "{\n"
        f'  "big": {{\n{big_lines}\n  }},\n'
        '  "small": {\n'
        '    "a": 1,\n'
        '    "b": 2,\n'
        '    "c": 3,\n'
        '    "d": 4,\n'
        '    "e": 5\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=120, full_text_max_lines=10
    )
    h = JsonFileHandler()
    root = h.open_root(str(path), None, budget=budget)
    assert not isinstance(root, PreviewError)
    assert root.node_kind == NodeKind.MAPPING
    resolved = h.resolve_node_ref("/small", None)
    assert not isinstance(resolved, PreviewError)
    assert resolved.attributes.get("full_text") is True
    text = resolved.attributes.get("text", "")
    assert "[/small/a]" in text
    assert '"a": 1' in text
    assert "filler_0" not in text


def test_json_handler_drill_down_large_mapping_stays_structural(
    tmp_path: pathlib.Path,
) -> None:
    big_lines = ",\n".join(f'    "filler_{i}": {i}' for i in range(30))
    path = tmp_path / "nested.json"
    path.write_text(
        "{\n"
        f'  "big": {{\n{big_lines}\n  }},\n'
        '  "small": {\n'
        '    "a": 1,\n'
        '    "b": 2,\n'
        '    "c": 3,\n'
        '    "d": 4,\n'
        '    "e": 5\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    budget = PreviewBudget(
        preview_lines=20, value_preview_len=120, full_text_max_lines=3
    )
    h = JsonFileHandler()
    assert not isinstance(h.open_root(str(path), None, budget=budget), PreviewError)
    resolved = h.resolve_node_ref("/big", None)
    assert not isinstance(resolved, PreviewError)
    assert resolved.node_kind == NodeKind.MAPPING
    assert resolved.attributes.get("full_text") is not True


def test_yaml_handler_resolve_unknown_path_unknown_node_ref(tmp_path) -> None:
    pytest.importorskip("yaml")
    path = tmp_path / "map.yaml"
    path.write_text("a: 1\n", encoding="utf-8")
    h = YamlFileHandler()
    assert not isinstance(h.open_root(str(path), None), PreviewError)
    err = h.resolve_node_ref("/missing", None)
    assert isinstance(err, PreviewError)
    assert err.code == INPUT_ERROR_UNKNOWN_NODE_REF


def test_yaml_handler_resolve_pointer_escape_in_key(tmp_path) -> None:
    """RFC6901 ~1 for / in key, ~0 for literal ~ in key."""
    pytest.importorskip("yaml")
    path = tmp_path / "esc.yaml"
    path.write_text('"a/b": 99\n"wave~tilde": 1\n', encoding="utf-8")
    h = YamlFileHandler()
    assert not isinstance(h.open_root(str(path), None), PreviewError)
    slash_key = h.resolve_node_ref("/a~1b", None)
    assert not isinstance(slash_key, PreviewError)
    assert slash_key.node_kind == NodeKind.SCALAR
    assert slash_key.attributes.get("value") == "99"
    tilde_key = h.resolve_node_ref("/wave~0tilde", None)
    assert not isinstance(tilde_key, PreviewError)
    assert tilde_key.node_kind == NodeKind.SCALAR
    assert tilde_key.attributes.get("value") == "1"


def test_jsonl_handler_open_root_lines_kind(tmp_path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text('{"x":1}\n', encoding="utf-8")
    result = JsonLinesFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.LINES


def test_jsonl_handler_open_root_multiline_children(tmp_path) -> None:
    """Root lines: two children with node_ref 0/1 and raw line text."""
    path = tmp_path / "multi.jsonl"
    path.write_text('{"x": 1}\n{"y": 2}\n', encoding="utf-8")
    result = JsonLinesFileHandler().open_root(str(path), None)
    assert not isinstance(result, PreviewError)
    assert result.node_kind == NodeKind.LINES
    children = result.children
    assert len(children) == 2
    assert children[0].node_ref == "0"
    assert children[0].attributes["value"] == '{"x": 1}'
    assert children[1].node_ref == "1"
    assert children[1].attributes["value"] == '{"y": 2}'


def test_jsonl_handler_resolve_node_ref_json_object_mapping_child(tmp_path) -> None:
    """Drill-in parses line as JSON; root matches _json_value_to_node object shape."""
    path = tmp_path / "doc.jsonl"
    path.write_text('{"a": 1}\n', encoding="utf-8")
    h = JsonLinesFileHandler()
    opened = h.open_root(str(path), None)
    assert not isinstance(opened, PreviewError)
    resolved = h.resolve_node_ref("0", None)
    assert not isinstance(resolved, PreviewError)
    assert resolved.node_kind == NodeKind.MAPPING
    assert resolved.node_ref == ""
    pairs = resolved.children
    assert len(pairs) == 1
    assert pairs[0].name == "a"
    assert pairs[0].attributes.get("value_kind") == "int"


def test_jsonl_handler_resolve_invalid_json_line_file_structure_error(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("not valid json\n", encoding="utf-8")
    h = JsonLinesFileHandler()
    assert not isinstance(h.open_root(str(path), None), PreviewError)
    err = h.resolve_node_ref("0", None)
    assert isinstance(err, PreviewError)
    assert err.code == FILE_STRUCTURE_ERROR


def test_jsonl_handler_resolve_node_ref_out_of_range_unknown_ref(tmp_path) -> None:
    path = tmp_path / "one.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    h = JsonLinesFileHandler()
    assert not isinstance(h.open_root(str(path), None), PreviewError)
    err = h.resolve_node_ref("3", None)
    assert isinstance(err, PreviewError)
    assert err.code == INPUT_ERROR_UNKNOWN_NODE_REF
    assert err.details is not None
    assert err.details.get("node_ref") == "3"


def test_jsonl_handler_resolve_non_integer_node_ref_unknown(tmp_path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    h = JsonLinesFileHandler()
    assert not isinstance(h.open_root(str(path), None), PreviewError)
    err = h.resolve_node_ref("abc", None)
    assert isinstance(err, PreviewError)
    assert err.code == INPUT_ERROR_UNKNOWN_NODE_REF
    assert err.details == {"node_ref": "abc"}


def test_universal_file_preview_whitelisted_for_read_only_batch() -> None:
    """Read-only batch allows universal_file_preview."""
    assert "universal_file_preview" in READ_ONLY_BATCH_WHITELIST


@pytest.mark.asyncio
async def test_universal_file_preview_execute_budget_py_mock_db() -> None:
    """Call execute with mocked DB: repo root from projectid resolves budget.py."""
    mock_db = _mock_db_for_root(_repo_root(), _repo_project_id())

    cmd = UniversalFilePreviewCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=mock_db
    ):
        params = cmd.validate_params(
            {
                "project_id": _repo_project_id(),
                "file_path": "code_analysis/commands/universal_file_preview/budget.py",
            }
        )
        result = await cmd.execute(**params)

    assert isinstance(result, SuccessResult)
    focus_text = (result.data or {}).get("focus", {}).get("text")
    assert isinstance(focus_text, str)
    assert focus_text.strip()


@pytest.mark.asyncio
async def test_universal_file_preview_md_annotated_full_text_without_session(
    tmp_path: pathlib.Path,
) -> None:
    """Preview without session_id still passes budget to MarkdownFileHandler."""
    root = tmp_path
    (root / "projectid").write_text(
        json.dumps({"id": _MD_PREVIEW_PID}), encoding="utf-8"
    )
    md = root / "notes.md"
    md.write_text("# Title\n\nBody line.\n", encoding="utf-8")

    mock_db = _mock_db_for_root(root, _MD_PREVIEW_PID)

    cmd = UniversalFilePreviewCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=mock_db
    ):
        params = cmd.validate_params(
            {
                "project_id": _MD_PREVIEW_PID,
                "file_path": "notes.md",
                "full_text_max_lines": 9999,
            }
        )
        result = await cmd.execute(**params)

    assert isinstance(result, SuccessResult)
    focus = (result.data or {}).get("focus", {})
    assert isinstance(focus.get("node_ref"), int)
    focus_text = focus.get("text") or (focus.get("attributes") or {}).get("text")
    assert isinstance(focus_text, str)
    assert "# Title" in focus_text


@pytest.mark.asyncio
async def test_universal_file_preview_md_empty_node_ref_same_as_omit(
    tmp_path: pathlib.Path,
) -> None:
    """Blank node_ref must not drill into section-tree root; same as omitted."""
    root = tmp_path
    (root / "projectid").write_text(
        json.dumps({"id": _MD_EMPTY_REF_PID}), encoding="utf-8"
    )
    md = root / "notes.md"
    md.write_text("# Title\n\nBody line.\n", encoding="utf-8")

    mock_db = _mock_db_for_root(root, _MD_EMPTY_REF_PID)

    cmd = UniversalFilePreviewCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=mock_db
    ):
        base = {
            "project_id": _MD_EMPTY_REF_PID,
            "file_path": "notes.md",
            "full_text_max_lines": 9999,
        }
        omitted = await cmd.execute(**cmd.validate_params(base))
        empty_ref = await cmd.execute(**cmd.validate_params({**base, "node_ref": ""}))
        whitespace = await cmd.execute(
            **cmd.validate_params({**base, "node_ref": "   "})
        )

    for result in (omitted, empty_ref, whitespace):
        assert isinstance(result, SuccessResult)
        focus = (result.data or {}).get("focus", {})
        assert isinstance(focus.get("node_ref"), int)
        assert int((result.data or {}).get("total_blocks") or 0) >= 1


@pytest.mark.asyncio
async def test_universal_file_preview_md_full_text_empty_draft_reads_original(
    tmp_path: pathlib.Path,
) -> None:
    """Text edit session previews draft path; empty draft falls back to source file."""
    root = tmp_path
    (root / "projectid").write_text(
        json.dumps({"id": _MD_DRAFT_PID}), encoding="utf-8"
    )
    md = root / "test.md"
    md.write_text("# Hello\n\nWorld\n", encoding="utf-8")

    mock_db = _mock_db_for_root(root, _MD_DRAFT_PID)

    open_cmd = UniversalFileOpenCommand()
    preview_cmd = UniversalFilePreviewCommand()
    close_cmd = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=mock_db
    ):
        opened = await open_cmd.execute(
            **open_cmd.validate_params(
                {
                    "project_id": _MD_DRAFT_PID,
                    "file_path": "test.md",
                }
            )
        )
        assert isinstance(opened, SuccessResult)
        sid = str(opened.data["session_id"])
        draft = md.with_suffix(md.suffix + ".draft")
        draft.write_text("", encoding="utf-8")
        result = await preview_cmd.execute(
            **preview_cmd.validate_params(
                {
                    "project_id": _MD_DRAFT_PID,
                    "file_path": "test.md",
                    "session_id": sid,
                    "full_text_max_lines": 9999,
                }
            )
        )
        await close_cmd.execute(
            **close_cmd.validate_params(
                {"project_id": "md-draft-preview-proj", "session_id": sid}
            )
        )

    assert isinstance(result, SuccessResult)
    focus = (result.data or {}).get("focus", {})
    assert isinstance(focus.get("node_ref"), int)
    focus_text = focus.get("text") or (focus.get("attributes") or {}).get("text") or ""
    assert "# Hello" in focus_text
    assert "World" in focus_text
    assert int((result.data or {}).get("total_blocks") or 0) > 0


@pytest.mark.asyncio
async def test_open_create_md_initial_content_preview_full_text(
    tmp_path: pathlib.Path,
) -> None:
    """create=True must persist initial_content for text formats before preview."""
    root = tmp_path
    (root / "projectid").write_text(
        json.dumps({"id": _MD_CREATE_PID}), encoding="utf-8"
    )

    mock_db = _mock_db_for_root(root, _MD_CREATE_PID)

    open_cmd = UniversalFileOpenCommand()
    preview_cmd = UniversalFilePreviewCommand()
    close_cmd = UniversalFileCloseCommand()
    with patch.object(
        BaseMCPCommand, "_open_database_from_config", return_value=mock_db
    ):
        opened = await open_cmd.execute(
            **open_cmd.validate_params(
                {
                    "project_id": _MD_CREATE_PID,
                    "file_path": "test.md",
                    "create": True,
                    "initial_content": "# Hello\n\nWorld\n",
                }
            )
        )
        assert isinstance(opened, SuccessResult)
        sid = str(opened.data["session_id"])
        md = root / "test.md"
        assert md.read_text(encoding="utf-8") == "# Hello\n\nWorld\n"
        result = await preview_cmd.execute(
            **preview_cmd.validate_params(
                {
                    "project_id": _MD_CREATE_PID,
                    "file_path": "test.md",
                    "session_id": sid,
                    "full_text_max_lines": 9999,
                }
            )
        )
        await close_cmd.execute(
            **close_cmd.validate_params(
                {"project_id": "md-create-preview-proj", "session_id": sid}
            )
        )

    assert isinstance(result, SuccessResult)
    focus = (result.data or {}).get("focus", {})
    assert isinstance(focus.get("node_ref"), int)
    text = focus.get("text") or (focus.get("attributes") or {}).get("text") or ""
    assert "# Hello" in text
    assert "World" in text
    assert int((result.data or {}).get("total_blocks") or 0) > 0
