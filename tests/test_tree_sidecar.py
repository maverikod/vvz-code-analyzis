"""Tests for CST ``.cst/*.tree`` sidecar persistence."""

from __future__ import annotations

from pathlib import Path

from code_analysis.core.cst_tree.tree_builder import create_tree_from_code, remove_tree
from code_analysis.core.cst_tree.tree_sidecar import (
    compute_source_sha256_hex,
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
