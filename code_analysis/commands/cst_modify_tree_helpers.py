"""
Helpers for CST modify tree command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from ..core.cst_tree.models import ROOT_NODE_ID_SENTINEL
from ..cst_query import query_source


class InvalidNodeIdError(ValueError):
    """Raised when a mutation target ID is missing, empty, or not valid UUID4."""

    pass


def _is_valid_uuid4(value: Optional[str]) -> bool:
    """Return True if value is non-empty and valid UUID4 string; otherwise False."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    try:
        u = uuid.UUID(s, version=4)
        return str(u) == s
    except (ValueError, TypeError):
        return False


def _require_uuid4_mutation_target(
    value: Optional[str],
    field_name: str,
    *,
    allow_root: bool = False,
) -> None:
    """
    Validate mutation target ID: must be non-empty and UUID4 (or __root__ if allowed).
    Raises InvalidNodeIdError on failure (fail-fast).
    """
    if not value or not isinstance(value, str):
        raise InvalidNodeIdError(
            f"{field_name} is required and must be a non-empty UUID4 string; got empty or non-string"
        )
    s = value.strip()
    if not s:
        raise InvalidNodeIdError(
            f"{field_name} must be a non-empty UUID4 string; got empty or whitespace"
        )
    if allow_root and s == ROOT_NODE_ID_SENTINEL:
        return
    if not _is_valid_uuid4(s):
        raise InvalidNodeIdError(
            f"{field_name} must be a valid UUID4 (e.g. from cst_find_node or cst_get_node_info); got {s!r}"
        )


def _find_tree_node_id_by_position(
    tree: Any, start_line: int, start_col: int, end_line: int, end_col: int
) -> Optional[str]:
    """Find tree's node_id for metadata matching given position."""
    for nid, meta in tree.metadata_map.items():
        if (
            meta.start_line == start_line
            and meta.start_col == start_col
            and meta.end_line == end_line
            and meta.end_col == end_col
        ):
            return nid
    return None


def _resolve_to_replaceable_node_id(tree: Any, node_id: str) -> str:
    """
    Resolve node_id to the replaceable ancestor (direct child of Module or
    IndentedBlock). tree_modifier replace only works on body statements.
    """
    meta = tree.metadata_map.get(node_id)
    if not meta or not getattr(meta, "parent_id", None):
        return node_id
    current_id = node_id
    while True:
        meta = tree.metadata_map.get(current_id)
        if not meta:
            return node_id
        parent_id = getattr(meta, "parent_id", None)
        if not parent_id:
            return current_id
        parent_meta = tree.metadata_map.get(parent_id)
        if not parent_meta:
            return current_id
        parent_type = getattr(parent_meta, "type", "") or ""
        if parent_type in ("Module", "IndentedBlock"):
            return current_id
        current_id = parent_id


def _expand_replace_many_operations(
    operations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Expand replace_many ops into multiple replace ops.
    Validates replacements (selector + code/code_lines) and returns
    a flat list of replace ops. Does not validate tree or selector matches.
    """
    expanded: List[Dict[str, Any]] = []
    for op in operations:
        if op.get("action") == "replace_many":
            replacements = op.get("replacements")
            if not isinstance(replacements, list) or len(replacements) == 0:
                raise ValueError("replace_many requires non-empty list 'replacements'")
            for i, r in enumerate(replacements):
                if not isinstance(r, dict):
                    raise ValueError(
                        f"replace_many.replacements[{i}] must be an object"
                    )
                sel = r.get("selector")
                if not sel:
                    raise ValueError(
                        f"replace_many.replacements[{i}] must have 'selector'"
                    )
                code = r.get("code")
                code_lines = r.get("code_lines")
                if not code and not code_lines:
                    raise ValueError(
                        f"replace_many.replacements[{i}] must have 'code' or 'code_lines'"
                    )
                expanded.append(
                    {
                        "action": "replace",
                        "selector": sel,
                        "match_index": r.get("match_index"),
                        "code": code,
                        "code_lines": code_lines,
                    }
                )
        else:
            expanded.append(op)
    return expanded


def _resolve_selector_to_tree_node_ids(
    tree: Any, selector: str, match_index: Optional[int], replace_all: bool
) -> List[str]:
    """
    Resolve selector to tree's node_ids (UUIDs in node_map).
    Uses query_source for matches, then finds tree metadata by position.
    """
    source = tree.module.code
    matches = query_source(source, selector, include_code=False)
    if not matches:
        return []
    node_ids: List[str] = []
    if replace_all:
        for m in matches:
            nid = _find_tree_node_id_by_position(
                tree, m.start_line, m.start_col, m.end_line, m.end_col
            )
            if nid:
                node_ids.append(nid)
    else:
        idx = match_index if match_index is not None else 0
        if 0 <= idx < len(matches):
            m = matches[idx]
            nid = _find_tree_node_id_by_position(
                tree, m.start_line, m.start_col, m.end_line, m.end_col
            )
            if nid:
                node_ids.append(nid)
    return node_ids
