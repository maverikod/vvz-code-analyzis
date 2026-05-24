"""
XPathLikeFilter universal structural engine for paginated search sessions.

Evaluates XPath-like selectors over validated TreeRepresentation data with
uniform semantics across indexed, in-memory, dynamic, and draft-session sources.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from code_analysis.core.search_session.tree_representation import TreeRepresentationRef


class TreeSourceKind(str, Enum):
    """Classification of tree data source for structural filtering."""

    indexed = "indexed"
    in_memory = "in_memory"
    dynamic = "dynamic"
    draft_session = "draft_session"


@dataclass(frozen=True)
class TreeNodeMatch:
    """One tree node matched by an XPath-like structural query."""

    file_path: str
    stable_id: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class CompiledQuery:
    """Normalized XPath-like query prepared for evaluation (v1: validation only)."""

    normalized_query: str


def compile_xpath_like(query: str) -> CompiledQuery:
    """Validate and normalize an XPath-like selector string."""
    if not query or not query.strip():
        raise ValueError("xpath-like query must not be empty")
    return CompiledQuery(normalized_query=query.strip())


def filter_tree_nodes(
    *,
    tree_ref: TreeRepresentationRef,
    query: str,
    source_kind: TreeSourceKind,
    node_loader: Callable[[TreeRepresentationRef], list[TreeNodeMatch]],
) -> list[TreeNodeMatch]:
    """Evaluate an XPath-like query against nodes loaded from *tree_ref*.

    Version 1 validates *query* and delegates node materialization to
    *node_loader* so indexer, database, dynamic, and draft loaders plug in
    without duplicating the selector engine. *source_kind* is accepted for
    uniform call sites; loader routing by source is deferred to later versions.
    """
    _ = source_kind
    compile_xpath_like(query)
    return node_loader(tree_ref)


__all__ = [
    "CompiledQuery",
    "TreeNodeMatch",
    "TreeSourceKind",
    "compile_xpath_like",
    "filter_tree_nodes",
]
