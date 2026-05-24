"""Tests for CST ``.cst/*.tree`` sidecar persistence."""

from __future__ import annotations

from pathlib import Path

from code_analysis.core.cst_tree.models import TreeOperation, TreeOperationType
from code_analysis.core.cst_tree.tree_builder import create_tree_from_code, remove_tree
from code_analysis.core.cst_tree.tree_modifier import modify_tree
from code_analysis.core.cst_tree.tree_sidecar import (
    compute_source_sha256_hex,
    pending_sidecar_path_for_py,
    promote_pending_sidecar_to_final,
    read_sidecar_payload,
    render_sidecar_file,
    sidecar_path_for_py,
    tree_to_sidecar_payload,
    verify_sidecar_against_source,
    write_sidecar_atomic,
)


def test_sidecar_path_next_to_py(tmp_path: Path) -> None:
    p = tmp_path / "pkg" / "mod.py"
    assert sidecar_path_for_py(p) == tmp_path / "pkg" / ".cst" / "mod.tree"


def test_verify_sidecar_sha(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    src = "x = 1\n"
    path.write_text(src, encoding="utf-8")
    tree = create_tree_from_code(str(path), src)
    try:
        payload = tree_to_sidecar_payload(tree)
        assert verify_sidecar_against_source(src, payload)
        assert not verify_sidecar_against_source(src + "\n# touch\n", payload)
    finally:
        remove_tree(tree.tree_id)


def test_write_read_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "b.py"
    src = "def f():\n    return 2\n"
    path.write_text(src, encoding="utf-8")
    tree = create_tree_from_code(str(path), src)
    try:
        write_sidecar_atomic(path, tree)
        raw = sidecar_path_for_py(path).read_text(encoding="utf-8")
        assert raw.startswith("CST_TREE_V1 sha256=")
        loaded = read_sidecar_payload(path)
        assert loaded is not None
        assert loaded["source_sha256"] == compute_source_sha256_hex(tree.module.code)
        assert verify_sidecar_against_source(tree.module.code, loaded)
    finally:
        remove_tree(tree.tree_id)


def test_render_parse_roundtrip_dict() -> None:
    payload = {
        "format_version": 1,
        "source_sha256": "a" * 64,
        "root_node_id": "rid",
        "path_to_node_id": {"0": "nid"},
        "metadata_map": {},
        "parent_map": {},
        "node_id_aliases": {},
    }
    text = render_sidecar_file(payload)
    assert text.splitlines()[0] == f"CST_TREE_V1 sha256={'a' * 64}"


def test_pending_sidecar_when_py_missing(tmp_path: Path) -> None:
    """Sidecar is written under ``.cst/_pending/`` before ``.py`` exists on disk."""
    path = tmp_path / "new_module.py"
    src = "x = 1\n"
    tree = create_tree_from_code(str(path), src)
    try:
        assert not path.is_file()
        written = write_sidecar_atomic(path, tree)
        pending = pending_sidecar_path_for_py(path)
        final = sidecar_path_for_py(path)
        assert written == pending
        assert pending.is_file()
        assert not final.is_file()
        loaded = read_sidecar_payload(path)
        assert loaded is not None
        assert verify_sidecar_against_source(src, loaded)
    finally:
        remove_tree(tree.tree_id)


def test_promote_pending_sidecar_after_py_created(tmp_path: Path) -> None:
    """When ``.py`` appears, pending sidecar is renamed to ``.cst/{stem}.tree``."""
    path = tmp_path / "later.py"
    src = "def f():\n    return 1\n"
    tree = create_tree_from_code(str(path), src)
    try:
        write_sidecar_atomic(path, tree)
        pending = pending_sidecar_path_for_py(path)
        final = sidecar_path_for_py(path)
        assert pending.is_file()

        path.write_text(src, encoding="utf-8")
        promoted = promote_pending_sidecar_to_final(path)
        assert promoted == final
        assert final.is_file()
        assert not pending.is_file()
        assert read_sidecar_payload(path) is not None
    finally:
        remove_tree(tree.tree_id)


def test_modify_tree_writes_pending_sidecar_without_py_file(tmp_path: Path) -> None:
    path = tmp_path / "draft_only.py"
    tree = create_tree_from_code(str(path), "a = 1\n")
    tree_id = tree.tree_id
    pending = pending_sidecar_path_for_py(path)
    try:
        modify_tree(
            tree_id,
            [
                TreeOperation(
                    action=TreeOperationType.REPLACE,
                    node_id=next(
                        nid
                        for nid, meta in tree.metadata_map.items()
                        if meta.type == "Assign"
                    ),
                    code_lines=["a = 2"],
                )
            ],
        )
        assert not path.is_file()
        assert pending.is_file()
    finally:
        remove_tree(tree_id)
