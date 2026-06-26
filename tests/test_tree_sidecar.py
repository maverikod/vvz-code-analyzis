"""Tests for CST sibling ``<source>.tree`` sidecar persistence."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from code_analysis.core.cst_tree.tree_builder import create_tree_from_code, remove_tree
from code_analysis.core.cst_tree.tree_sidecar import (
    compute_source_sha256_hex,
    read_sidecar_payload,
    render_sidecar_file,
    tree_to_sidecar_payload,
    verify_sidecar_against_source,
    write_sidecar_atomic,
)
from code_analysis.core.tree_file_write import (
    atomic_write_sibling_tree_file,
    match_file_owner,
)
from code_analysis.tree.sibling_convention import sibling_tree_path


def test_sidecar_path_next_to_py(tmp_path: Path) -> None:
    """Verify test sidecar path next to py."""
    p = tmp_path / "pkg" / "mod.py"
    assert (
        sibling_tree_path(p.resolve()) == (tmp_path / "pkg" / "mod.py.tree").resolve()
    )


def test_verify_sidecar_sha(tmp_path: Path) -> None:
    """Verify test verify sidecar sha."""
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
    """Verify test write read roundtrip."""
    path = tmp_path / "b.py"
    src = "def f():\n    return 2\n"
    path.write_text(src, encoding="utf-8")
    tree = create_tree_from_code(str(path), src)
    try:
        write_sidecar_atomic(path, tree)
        raw = sibling_tree_path(path.resolve()).read_text(encoding="utf-8")
        assert raw.startswith("CST_TREE_V1 sha256=")
        loaded = read_sidecar_payload(path)
        assert loaded is not None
        assert loaded["source_sha256"] == compute_source_sha256_hex(tree.module.code)
        assert verify_sidecar_against_source(tree.module.code, loaded)
    finally:
        remove_tree(tree.tree_id)


def test_render_parse_roundtrip_dict() -> None:
    """Verify test render parse roundtrip dict."""
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


@pytest.mark.skipif(sys.platform == "win32", reason="chown not supported on Windows")
def test_write_sidecar_atomic_matches_source_owner(tmp_path: Path) -> None:
    """Verify test write sidecar atomic matches source owner."""
    path = tmp_path / "owner.py"
    path.write_text("x = 1\n", encoding="utf-8")
    tree = create_tree_from_code(str(path), "x = 1\n")
    sidecar = sibling_tree_path(path.resolve())
    try:
        with patch(
            "code_analysis.core.cst_tree.tree_sidecar.match_file_owner"
        ) as chown:
            write_sidecar_atomic(path, tree)
            chown.assert_called_once_with(sidecar.resolve(), path.resolve())
    finally:
        remove_tree(tree.tree_id)


@pytest.mark.skipif(sys.platform == "win32", reason="chown not supported on Windows")
def test_atomic_write_sibling_tree_file_applies_chown(tmp_path: Path) -> None:
    """Verify test atomic write sibling tree file applies chown."""
    source = tmp_path / "data.json"
    source.write_text("{}", encoding="utf-8")
    sidecar = sibling_tree_path(source.resolve())
    with patch("code_analysis.core.tree_file_write.os.chown") as chown:
        atomic_write_sibling_tree_file(
            source_abs=source,
            sidecar_path=sidecar,
            text='{"source_sha256": "a" * 64}\n',
        )
        st = os.stat(source)
        chown.assert_called_once_with(sidecar.resolve(), st.st_uid, st.st_gid)


def test_match_file_owner_noop_on_windows(tmp_path: Path) -> None:
    """Verify test match file owner noop on windows."""
    target = tmp_path / "t.tree"
    target.write_text("x", encoding="utf-8")
    reference = tmp_path / "s.py"
    reference.write_text("y", encoding="utf-8")
    with patch.object(sys, "platform", "win32"):
        match_file_owner(target, reference)
