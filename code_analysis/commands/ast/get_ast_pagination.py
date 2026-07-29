"""
Node flattening for get_ast's paginated node-listing response (TODO 1b6cc124).

``get_ast``'s raw ``ast`` payload (``include_json``) returns the whole tree,
which is unusable on large files. When a caller passes any pagination or
node-projection parameter, ``get_ast`` switches to a bounded, paginated
node-listing response built by walking a freshly-parsed ``ast.Module`` tree
-- never the DB-stored ``ast_json`` blob, whose shape depends on whatever
wrote it and is not guaranteed to align with Python's ``ast`` node classes --
and slicing it with the same list-pagination convention already used by
``list_project_files`` / ``list_code_entities`` / etc.
(:mod:`code_analysis.core.list_pagination`).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Sequence

# Node attributes ever exposed per flattened node. ``node_type`` is always
# present; the ``fields`` schema param may narrow this set further but never
# adds attributes outside it -- keeps the payload bounded and avoids exposing
# arbitrary ast-node attributes from client-supplied field names.
ALLOWED_NODE_FIELDS: tuple[str, ...] = (
    "lineno",
    "col_offset",
    "end_lineno",
    "end_col_offset",
    "name",
    "id",
)


def flatten_ast_nodes(
    tree: ast.AST,
    *,
    node_types: Optional[Sequence[str]] = None,
    fields: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Walk ``tree`` and return one flat dict per node (kind + selected fields).

    Args:
        tree: Parsed module (``ast.parse`` result).
        node_types: Optional allowlist of ``type(node).__name__`` values
            (e.g. ``["FunctionDef", "ClassDef"]``). ``None`` or empty means no
            filter (every node kind included).
        fields: Optional allowlist of field names to include per node, drawn
            from :data:`ALLOWED_NODE_FIELDS`. ``None`` or empty means include
            every field in :data:`ALLOWED_NODE_FIELDS` present on the node.

    Returns:
        Nodes in :func:`ast.walk` order (deterministic for a given parse),
        each ``{"node_type": str, <requested fields present on the node>}``.
    """
    allowed_types = set(node_types) if node_types else None
    selected_fields = (
        [f for f in fields if f in ALLOWED_NODE_FIELDS]
        if fields
        else list(ALLOWED_NODE_FIELDS)
    )

    out: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        kind = type(node).__name__
        if allowed_types is not None and kind not in allowed_types:
            continue
        entry: Dict[str, Any] = {"node_type": kind}
        for field_name in selected_fields:
            if hasattr(node, field_name):
                entry[field_name] = getattr(node, field_name)
        out.append(entry)
    return out
