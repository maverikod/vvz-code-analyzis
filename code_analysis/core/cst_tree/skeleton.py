"""
Build declarative overview for a CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional

from .models import CSTTree, TreeNodeMetadata

BODY_PLACEHOLDER_COMMENT = (
    "# Implementation hidden; request node by node_id for full code"
)
VISIBLE_KINDS = {"module", "import", "class", "function", "method"}


def build_declarative_overview(tree: CSTTree) -> tuple[str, List[Dict[str, Any]]]:
    """Return declarative overview text and compact outline nodes."""
    root_meta = tree.metadata_map.get(tree.root_node_id or "")
    if root_meta is None:
        return ("", [])

    lines: List[str] = []
    outline_nodes: List[Dict[str, Any]] = []
    module_docstring = _extract_docstring(tree.module.code)
    module_header = f"module [{root_meta.node_id}] {tree.file_path}"
    lines.append(module_header)
    outline_nodes.append(_outline_entry(root_meta, depth=0, signature=module_header))
    if module_docstring:
        lines.extend(_indent_block(_format_docstring(module_docstring), depth=1))

    for child_id in root_meta.children_ids:
        _append_visible_descendants(
            tree=tree,
            node_id=child_id,
            depth=1,
            lines=lines,
            outline_nodes=outline_nodes,
        )
    return ("\n".join(lines) + ("\n" if lines else ""), outline_nodes)


def skeleton_from_tree(tree: CSTTree) -> str:
    """Backward-compatible alias for the new declarative overview."""
    overview, _outline_nodes = build_declarative_overview(tree)
    return overview


def _append_node_overview(
    tree: CSTTree,
    node_id: str,
    depth: int,
    lines: List[str],
    outline_nodes: List[Dict[str, Any]],
) -> None:
    metadata = tree.metadata_map.get(node_id)
    node = tree.node_map.get(node_id)
    if metadata is None or node is None:
        return
    if metadata.kind not in VISIBLE_KINDS:
        return

    node_code = tree.module.code_for_node(node)
    signature = _build_signature(metadata, node_code)
    lines.append(f"{'    ' * depth}{signature}")
    outline_nodes.append(_outline_entry(metadata, depth=depth, signature=signature))

    docstring = _extract_docstring(node_code)
    if docstring:
        lines.extend(_indent_block(_format_docstring(docstring), depth=depth + 1))

    if metadata.kind in {"class", "module"}:
        for child_id in metadata.children_ids:
            _append_visible_descendants(
                tree=tree,
                node_id=child_id,
                depth=depth + 1,
                lines=lines,
                outline_nodes=outline_nodes,
            )
    elif metadata.kind in {"function", "method"}:
        lines.append(f"{'    ' * (depth + 1)}{BODY_PLACEHOLDER_COMMENT}")


def _append_visible_descendants(
    tree: CSTTree,
    node_id: str,
    depth: int,
    lines: List[str],
    outline_nodes: List[Dict[str, Any]],
) -> None:
    metadata = tree.metadata_map.get(node_id)
    if metadata is None:
        return
    if metadata.kind in VISIBLE_KINDS:
        _append_node_overview(
            tree=tree,
            node_id=node_id,
            depth=depth,
            lines=lines,
            outline_nodes=outline_nodes,
        )
        return
    for child_id in metadata.children_ids:
        _append_visible_descendants(
            tree=tree,
            node_id=child_id,
            depth=depth,
            lines=lines,
            outline_nodes=outline_nodes,
        )


def _build_signature(metadata: TreeNodeMetadata, code: str) -> str:
    prefix = f"[{metadata.node_id}] "
    if metadata.kind == "import":
        first_line = code.strip().splitlines()[0] if code.strip() else metadata.type
        return f"{prefix}{first_line}"

    header_lines: List[str] = []
    for line in code.splitlines():
        stripped = line.rstrip()
        if not stripped and not header_lines:
            continue
        header_lines.append(stripped)
        if stripped.strip().endswith(":"):
            break
    if not header_lines:
        header_lines = [metadata.type]
    header = " ".join(part.strip() for part in header_lines)
    return f"{prefix}{header}"


def _format_docstring(docstring: str) -> List[str]:
    return ['"""', *docstring.splitlines(), '"""']


def _indent_block(lines: List[str], depth: int) -> List[str]:
    prefix = "    " * depth
    return [f"{prefix}{line}" for line in lines]


def _outline_entry(
    metadata: TreeNodeMetadata,
    depth: int,
    signature: str,
) -> Dict[str, Any]:
    data = metadata.to_dict()
    data["depth"] = depth
    data["signature"] = signature
    return data


def _extract_docstring(code: str) -> Optional[str]:
    try:
        parsed = ast.parse(code)
    except SyntaxError:
        return None
    return ast.get_docstring(parsed)
