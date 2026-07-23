"""
Unit tests for search_paginated_cross_grep_evidence.py — the two helpers moved
verbatim out of the deleted project_cross_search_core.py (cross-search removal).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from code_analysis.commands.search_paginated_cross_grep_evidence import (
    is_structural_grep_evidence,
    normalize_file_path,
    normalize_grep_hit,
)


def test_normalize_file_path_makes_absolute_under_root_relative() -> None:
    """Absolute path under project_root -> project-relative posix path."""
    root = Path("/proj")
    assert normalize_file_path("/proj/pkg/mod.py", root) == "pkg/mod.py"


def test_normalize_file_path_no_root_strips_leading_dot_slash() -> None:
    """No project_root -> only ./-stripping, no absolutization."""
    assert normalize_file_path("./pkg/mod.py") == "pkg/mod.py"


def test_is_structural_grep_evidence_requires_enriched_status() -> None:
    """Non-enriched status -> not structural evidence."""
    item = {
        "source": "grep_unindexed",
        "metadata": {"enrichment_status": "pending", "preview": "x", "node_ref": "n1"},
    }
    assert is_structural_grep_evidence(item) is False


def test_is_structural_grep_evidence_accepts_enriched_with_node_ref() -> None:
    """Enriched + preview + node_ref + structural source -> True."""
    item = {
        "source": "grep_changed",
        "metadata": {
            "enrichment_status": "enriched",
            "preview": "def foo(): ...",
            "node_ref": "n1",
        },
    }
    assert is_structural_grep_evidence(item) is True


def test_is_structural_grep_evidence_rejects_non_structural_source() -> None:
    """Enriched + node_ref but source not in STRUCTURAL_GREP_SOURCES -> False."""
    item = {
        "source": "grep",
        "metadata": {
            "enrichment_status": "enriched",
            "preview": "x",
            "node_ref": "n1",
        },
    }
    assert is_structural_grep_evidence(item) is False


def test_normalize_grep_hit_maps_relative_path_and_metadata() -> None:
    """normalize_grep_hit: relative_path wins over file_path; metadata carries node_ref."""
    row = {
        "relative_path": "pkg/mod.py",
        "file_path": "/abs/pkg/mod.py",
        "line_number": "42",
        "source": "grep_changed",
        "node_ref": "n1",
        "line": "def foo(): pass",
    }
    out = normalize_grep_hit(row, "foo", None)
    assert out["file_path"] == "pkg/mod.py"
    assert out["line_start"] == 42
    assert out["source"] == "grep_changed"
    assert out["metadata"]["node_ref"] == "n1"
    assert out["metadata"]["pattern"] == "foo"
