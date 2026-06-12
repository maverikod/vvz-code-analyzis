"""
TreeBuilder (C-011): canonical unified writer of three-section TreeFiles (C-003).

HandlerRegistry → FormatHandler.mark → NodeIdMap.build → atomic sibling write.
Does NOT use recreate_tree_from_content or TreeFormatKind (legacy parity oracle).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from code_analysis.core.tree_file_write import atomic_write_sibling_tree_file
from code_analysis.core.tree_lifecycle.node_id_map import (
    ChecksumsSection,
    DiscoveredNode,
    MapSection,
    NodeIdMap,
    compute_content_fingerprint,
    parse_tree_file,
    serialize_tree_file,
)
from code_analysis.tree.format_handler import FormatHandler
from code_analysis.tree.handler_registry import HandlerRegistry
from code_analysis.tree.tree_node import TreeNode

if TYPE_CHECKING:
    from code_analysis.core.search_session.tree_representation import (
        TreeRepresentationRef,
    )


def _discovered_nodes_from_tree_nodes(nodes: List[TreeNode]) -> List[DiscoveredNode]:
    """Map parse_content nodes to NodeIdMap inputs."""
    out: List[DiscoveredNode] = []
    for node in nodes:
        fp = compute_content_fingerprint(node.content)
        out.append(
            DiscoveredNode(
                content_fingerprint=fp,
                kind=node.kind,
                marker_short_id=node.short_id,
                attributes=dict(node.attributes),
            )
        )
    return out


def _first_root_stable_id(nodes: List[TreeNode]) -> str | None:
    """Return str(first.short_id) or None when empty."""
    if not nodes:
        return None
    return str(nodes[0].short_id)


def _load_prior_map(sidecar_path: Path) -> MapSection | None:
    """If sidecar exists and parses, return MAP; else None."""
    if not sidecar_path.is_file():
        return None
    try:
        text = sidecar_path.read_text(encoding="utf-8")
        return parse_tree_file(text).map
    except Exception:
        return None


class TreeBuilder:
    """TreeBuilder (C-011): unified HandlerRegistry writer."""

    @staticmethod
    def build(
        *,
        content: str,
        source_abs: Path,
        file_path: str,
        content_checksum: str,
        registry: Optional[HandlerRegistry] = None,
    ) -> TreeRepresentationRef:
        """Build and atomically write a three-section sibling TreeFile.

        Resolves a FormatHandler via HandlerRegistry, marks content for the TREE
        section, builds MAP/CHECKSUMS via NodeIdMap, and writes the sibling
        ``.tree`` sidecar atomically.

        Args:
            content: Unmarked SourceFile body text.
            source_abs: Absolute path to the source file (selects handler).
            file_path: Project-relative path stored in the returned ref.
            content_checksum: SHA-256 hex digest of *content* (CHECKSUMS section).
            registry: Optional HandlerRegistry; defaults to
                ``HandlerRegistry.default_registry()``.

        Returns:
            TreeRepresentationRef with *content_checksum* in the ref and
            ``source_sha256`` recorded in the on-disk CHECKSUMS section.

        Raises:
            HandlerNotFoundError: No handler registered for *source_abs* suffix.
            ValueError: No addressable nodes discovered from *content*.
            OSError: Sidecar directory creation or atomic write failure.
            NodeIdMapError: MAP/TREE validation failure during build or repair.
            Other handler or parse errors propagate unchanged.
        """
        reg = registry if registry is not None else HandlerRegistry.default_registry()
        handler: FormatHandler = reg.resolve(source_abs)
        marked_text = handler.mark(content)
        nodes = handler.parse_content(source_abs, content)
        discovered = _discovered_nodes_from_tree_nodes(nodes)
        if not discovered:
            raise ValueError("TreeBuilder.build requires at least one addressable node")
        sidecar_path = handler.sidecar_path(source_abs)
        prior_map = _load_prior_map(sidecar_path)
        checksums: ChecksumsSection = {"source_sha256": content_checksum}
        sections, node_map = NodeIdMap.build(
            tree_marked_text=marked_text,
            discovered_nodes=discovered,
            source_sha256=content_checksum,
            prior_map=prior_map,
        )
        if prior_map is not None:
            sections = node_map.validate_and_repair(
                tree_marked_text=marked_text,
                discovered_nodes=discovered,
                checksums=checksums,
            )
        file_text = serialize_tree_file(sections)
        atomic_write_sibling_tree_file(
            source_abs=source_abs,
            sidecar_path=sidecar_path,
            text=file_text,
        )
        from code_analysis.core.search_session.tree_representation import (
            TreeRepresentationRef,
        )

        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=_first_root_stable_id(nodes),
        )


__all__ = ["TreeBuilder"]
