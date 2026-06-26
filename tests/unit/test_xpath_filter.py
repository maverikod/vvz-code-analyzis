"""Unit tests for XPathLikeFilter engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_analysis.core.search_session.tree_representation import TreeRepresentationRef
from code_analysis.core.search_session.xpath_filter import (
    TreeNodeMatch,
    TreeSourceKind,
    compile_xpath_like,
    filter_tree_nodes,
)


def _sample_tree_ref() -> TreeRepresentationRef:
    """Return sample tree ref."""
    return TreeRepresentationRef(
        file_path="src/app.py",
        sidecar_path=Path("/tmp/app.tree"),
        content_checksum="a" * 64,
        root_stable_id="root-1",
    )


def test_compile_xpath_like_rejects_empty_query() -> None:
    """Verify test compile xpath like rejects empty query."""
    with pytest.raises(ValueError, match="must not be empty"):
        compile_xpath_like("")
    with pytest.raises(ValueError, match="must not be empty"):
        compile_xpath_like("   ")


def test_compile_xpath_like_normalizes_whitespace() -> None:
    """Verify test compile xpath like normalizes whitespace."""
    compiled = compile_xpath_like("  class[name='Foo']  ")
    assert compiled.normalized_query == "class[name='Foo']"


def test_filter_tree_nodes_delegates_to_node_loader() -> None:
    """Verify test filter tree nodes delegates to node loader."""
    tree_ref = _sample_tree_ref()
    expected = [
        TreeNodeMatch(
            file_path="src/app.py",
            stable_id="node-42",
            start_line=10,
            end_line=20,
        )
    ]
    calls: list[TreeRepresentationRef] = []

    def loader(ref: TreeRepresentationRef) -> list[TreeNodeMatch]:
        """Return loader."""
        calls.append(ref)
        return expected

    result = filter_tree_nodes(
        tree_ref=tree_ref,
        query="function[name='run']",
        source_kind=TreeSourceKind.indexed,
        node_loader=loader,
    )
    assert result == expected
    assert calls == [tree_ref]
