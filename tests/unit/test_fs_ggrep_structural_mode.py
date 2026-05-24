"""Unit tests for fs_grep structural GrepSearchMode integration."""

from __future__ import annotations

from pathlib import Path

from code_analysis.commands.fs_grep_structural_integration import (
    DEFAULT_GREP_MODE,
    GrepSearchMode,
    apply_grep_mode,
    enrich_line_matches_structural,
)
from code_analysis.core.cst_tree.tree_builder import create_tree_from_code, remove_tree
from code_analysis.core.cst_tree.tree_sidecar import write_sidecar_atomic


def test_default_grep_mode_is_structural() -> None:
    assert DEFAULT_GREP_MODE == GrepSearchMode.structural


def test_apply_grep_mode_classic_line_returns_unchanged() -> None:
    project_root = Path("/tmp/unused")
    matches = [
        {
            "relative_path": "src/app.py",
            "line_number": 1,
            "line": "needle",
        }
    ]

    result = apply_grep_mode(
        mode=GrepSearchMode.classic_line,
        project_root=project_root,
        file_path="src/app.py",
        line_matches=matches,
    )

    assert result.matches == matches
    assert result.structural_evidence_eligibility.value == "ineligible"
    assert "preview_ref" not in result.matches[0]


def test_apply_grep_mode_structural_adds_preview_ref_when_tree_valid(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    rel = "mod.py"
    py_path = project_root / rel
    source = "def find_it():\n    return 'needle'\n"
    py_path.write_text(source, encoding="utf-8")

    tree = create_tree_from_code(str(py_path), source)
    try:
        py_path.write_text(tree.module.code, encoding="utf-8")
        write_sidecar_atomic(py_path, tree)
    finally:
        remove_tree(tree.tree_id)

    matches = [
        {
            "relative_path": rel,
            "line_number": 1,
            "line": "def find_it():",
            "node_ref": "node-stable-1",
            "selector": "function[name='find_it']",
        }
    ]

    result = apply_grep_mode(
        mode=GrepSearchMode.structural,
        project_root=project_root,
        file_path=rel,
        line_matches=matches,
    )

    assert len(result.matches) == 1
    assert result.structural_evidence_eligibility.value == "eligible"
    preview_ref = result.matches[0].get("preview_ref")
    assert isinstance(preview_ref, dict)
    assert preview_ref["file_path"] == rel
    assert preview_ref["node_id"] == "node-stable-1"
    assert preview_ref["selector"] == "function[name='find_it']"


def test_enrich_line_matches_structural_skips_preview_when_tree_missing(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    rel = "missing_sidecar.py"
    (project_root / rel).write_text("x = 1\n", encoding="utf-8")

    matches = [{"relative_path": rel, "line_number": 1, "line": "x = 1"}]

    result = enrich_line_matches_structural(
        project_root=project_root,
        file_path=rel,
        line_matches=matches,
    )

    assert len(result) == 1
    assert "preview_ref" not in result[0]
