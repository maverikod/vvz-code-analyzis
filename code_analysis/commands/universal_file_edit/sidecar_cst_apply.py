"""
Sidecar-backed CST universal edit validation and synchronous batch apply.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

import libcst as cst

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.cst_modify_tree_ops_build import build_tree_operations
from code_analysis.commands.universal_file_edit.errors import (
    NESTED_BATCH_FORBIDDEN,
    PARSE_ERROR,
    error_result_for_edit,
    make_error,
)
from code_analysis.commands.universal_file_edit.session import EditSession
from code_analysis.core.cst_tree.models import CSTTree, ROOT_NODE_ID_SENTINEL
from code_analysis.core.cst_tree.tree_builder import (
    get_tree,
    load_file_to_tree,
    rollback_tree_to_code,
)
from code_analysis.core.cst_tree.tree_modifier import modify_tree
from code_analysis.core.cst_tree.tree_sidecar import write_sidecar_atomic


class StaleNodeIdError(ValueError):
    """Raised when a stable_id is not found in the current CST tree.

    Attributes:
        field: Name of the op field containing the stale id.
        stable_id: The stale stable_id value.
    """

    def __init__(self, message: str, *, field: str, stable_id: str) -> None:
        """Initialise StaleNodeIdError.

        Args:
            message: Human-readable error message.
            field: Name of the op dict field (node_id / parent_node_id / target_node_id).
            stable_id: The stale stable_id value that was not found.
        """
        super().__init__(message)
        self.field = field
        self.stable_id = stable_id


def _promote_leaf_ref_to_statement_line(tree: CSTTree, node_id: str) -> str:
    """Map preview leaf refs (Name, Integer, …) to enclosing ``SimpleStatementLine``.

    Annotated full-text and structured preview can surface inner-node stable_ids.
    ``universal_file_edit`` replace/delete must target the statement line, not a
    fine-grained leaf (see ``FINE_GRAINED_REPLACE_NODE_TYPES`` in CST modifier).
    """
    meta = tree.metadata_map.get(node_id)
    if meta is None:
        return node_id
    if meta.type in (
        "SimpleStatementLine",
        "FunctionDef",
        "AsyncFunctionDef",
        "ClassDef",
    ):
        return node_id
    if (meta.kind or "") in ("function", "method", "class", "import"):
        return node_id

    current = node_id
    stmt_line_id: Optional[str] = None
    while True:
        row = tree.metadata_map.get(current)
        if row is None:
            break
        if row.type == "SimpleStatementLine" and (row.kind or "") == "stmt":
            stmt_line_id = current
            break
        parent_id = row.parent_id
        if not parent_id:
            break
        current = parent_id
    return stmt_line_id if stmt_line_id else node_id


def _coalesce_node_ref_keys(op: Dict[str, Any]) -> Dict[str, Any]:
    """Map universal_file_preview ``node_ref`` aliases onto CST op field names."""
    m = dict(op)
    for ref_key, id_key in (
        ("node_ref", "node_id"),
        ("parent_node_ref", "parent_node_id"),
        ("target_node_ref", "target_node_id"),
    ):
        if ref_key in m and not m.get(id_key):
            m[id_key] = m[ref_key]
    return m


def _resolve_stable_to_span(op: Dict[str, Any], tree: CSTTree) -> Dict[str, Any]:
    """Replace stable_id in node refs with span-based node_id for modify_tree."""
    from code_analysis.core.cst_tree.tree_metadata import _resolve_node_id

    m = _coalesce_node_ref_keys(op)
    raw_action = m.get("action") or m.get("type") or ""
    action = str(raw_action).strip().lower()
    for field in ("node_id", "parent_node_id", "target_node_id"):
        raw = m.get(field)
        if not isinstance(raw, str) or not raw:
            continue
        if ":" not in raw:
            if raw == ROOT_NODE_ID_SENTINEL:
                m[field] = raw
                continue
            meta = tree.find_by_stable_id(raw)
            if meta is None:
                raise StaleNodeIdError(
                    f"stable_id '{raw}' not found in current CST tree. "
                    "Re-call universal_file_preview after each edit to obtain fresh node_ref values.",
                    field=field,
                    stable_id=raw,
                )
            raw = meta.node_id
        resolved = _resolve_node_id(tree, raw)
        if field == "node_id" and action in ("replace", "delete"):
            resolved = _promote_leaf_ref_to_statement_line(tree, resolved)
        m[field] = resolved
    return m


def _validate_replace_snippet_via_module(m: Dict[str, Any]) -> None:
    """Validate replace snippets as module statements (not bare expressions).

    Simple assignments such as ``DEFAULT_TIMEOUT = 60`` must parse as statements.
    ``tree_modifier_validate`` may otherwise treat inner ``Name`` targets as
    expressions and reject valid statement replacements.
    """
    action = str(m.get("action") or "").lower()
    if action != "replace":
        return
    raw_code = m.get("code")
    raw_lines = m.get("code_lines")
    if raw_lines is not None:
        if raw_code is not None:
            raise ValueError("Cannot provide both code and code_lines")
        text = "\n".join(str(line) for line in raw_lines)
    elif isinstance(raw_code, str):
        text = raw_code
    else:
        return
    if not text.strip():
        return
    source = text if text.endswith("\n") else text + "\n"
    try:
        mod = cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        raise ValueError(f"Invalid code syntax for replace: {exc}") from exc
    if not mod.body:
        raise ValueError("Invalid code syntax for replace: empty module body")
    normalized = mod.code
    if not normalized.endswith("\n"):
        normalized += "\n"
    m["code"] = normalized
    m.pop("code_lines", None)


def _normalized_cst_modify_operation(op: Dict[str, Any]) -> Dict[str, Any]:
    """Map universal-edit op keys into ``build_tree_operations`` / CST shape."""
    m = dict(op)
    raw_action = op.get("action")
    raw_type = op.get("type")
    if isinstance(raw_action, str) and raw_action.strip():
        m["action"] = raw_action.strip().lower()
    elif isinstance(raw_type, str) and raw_type.strip():
        m["action"] = raw_type.strip().lower()

    action = str(m.get("action") or "").lower()
    if "code" not in m and "code_lines" not in m:
        for alt_key in ("new_content", "content"):
            alt_val = m.get(alt_key)
            if isinstance(alt_val, str):
                m["code"] = alt_val
                break
    if action == "insert":
        target_nid = m.get("target_node_id")
        parent_nid = m.get("parent_node_id")
        pos_raw = m.get("position")
        pos_str = pos_raw.strip().lower() if isinstance(pos_raw, str) else None
        if target_nid and parent_nid:
            if pos_str in ("before", "after"):
                m.pop("parent_node_id", None)
            elif parent_nid == ROOT_NODE_ID_SENTINEL and pos_str in ("first", "last"):
                m.pop("target_node_id", None)
            else:
                raise ValueError(
                    "insert: provide either target_node_id with position before|after "
                    "or parent_node_id with position first|last|{after:N}, not both"
                )
        if target_nid and pos_str in ("before", "after"):
            pass
        elif parent_nid and isinstance(pos_raw, dict) and "after" in pos_raw:
            pass
        elif target_nid and pos_str in ("first", "last"):
            raise ValueError(
                "insert: position first|last requires parent_node_id; "
                "use target_node_id with position before|after for sibling-relative insert"
            )
        elif pos_str in ("before", "after") and not target_nid:
            raise ValueError(
                "insert: position before|after requires target_node_id "
                "(sibling node_ref from universal_file_preview)"
            )

    _validate_replace_snippet_via_module(m)
    return m


def _is_ancestor(
    tree: CSTTree, ancestor_stable_id: str, descendant_stable_id: str
) -> bool:
    """Return True if ancestor_stable_id is an ancestor of descendant_stable_id in tree.

    Args:
        tree: In-memory CST tree object.
        ancestor_stable_id: Stable ID of the potential ancestor node.
        descendant_stable_id: Stable ID of the potential descendant node.

    Returns:
        True if ancestor_stable_id is found in the parent chain of descendant_stable_id.
    """
    node_meta = tree.find_by_stable_id(descendant_stable_id)
    if node_meta is None:
        return False
    current_nid: Optional[str] = node_meta.node_id
    while current_nid is not None:
        parent_nid: Optional[str] = tree.parent_map.get(current_nid)
        if not parent_nid:
            return False
        parent_meta = tree.metadata_map.get(parent_nid)
        if parent_meta is None:
            return False
        if parent_meta.stable_id == ancestor_stable_id:
            return True
        current_nid = parent_nid
    return False


def validate_sidecar_nested_batch(
    operations: List[Dict[str, Any]],
    tree_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Validate that no ancestor-descendant pairs exist in the batch.

    For sidecar group only. Checks every pair of node_ids in the batch.
    If any node is an ancestor of another, rejects the entire batch.

    Args:
        operations: List of edit operation dicts with parent_node_id.
        tree_id: In-memory CST tree UUID for ancestor resolution.

    Returns:
        None when batch is valid;
        error dict with NESTED_BATCH_FORBIDDEN when invalid.
    """
    node_ids: List[str] = []
    for op in operations:
        raw = op.get("parent_node_id")
        if isinstance(raw, str) and raw:
            node_ids.append(raw)
    if len(node_ids) < 2 or tree_id is None:
        return None
    tree = get_tree(tree_id)
    if tree is None:
        return None
    for i, nid_a in enumerate(node_ids):
        for nid_b in node_ids[i + 1 :]:
            if _is_ancestor(tree, nid_a, nid_b) or _is_ancestor(tree, nid_b, nid_a):
                return cast(
                    Dict[str, Any],
                    make_error(
                        NESTED_BATCH_FORBIDDEN,
                        "Ancestor-descendant pair in batch",
                    ),
                )
    return None


def run_sidecar_cst_edit_batch(
    session: EditSession,
    operations: List[Dict[str, Any]],
) -> SuccessResult | ErrorResult:
    """Apply sidecar CST operations synchronously (for asyncio.to_thread)."""

    def _rollback_sidecar_session(
        tree_id: str,
        code: str,
        metadata_snapshot: Dict[str, Any],
    ) -> None:
        rollback_tree_to_code(
            tree_id,
            code,
            index_metadata_for_code=metadata_snapshot,
        )
        session.tree_id = tree_id
        restored = get_tree(tree_id)
        if restored is not None:
            write_sidecar_atomic(session.abs_path, restored)

    tid = session.tree_id
    tree = get_tree(tid) if tid else None
    if tree is None:
        try:
            tree = load_file_to_tree(str(session.abs_path))
        except FileNotFoundError as exc:
            return error_result_for_edit(
                str(exc),
                "FILE_NOT_FOUND",
                {"path": str(session.abs_path)},
            )
        except Exception as exc:
            return error_result_for_edit(
                str(exc),
                PARSE_ERROR,
                {"path": str(session.abs_path)},
            )
    session.tree_id = tree.tree_id

    batch_original_code = tree.module.code
    batch_original_tree_id = tree.tree_id
    batch_original_metadata = dict(tree.metadata_map)

    def _rollback_and_fail(err: ErrorResult) -> ErrorResult:
        _rollback_sidecar_session(
            batch_original_tree_id,
            batch_original_code,
            batch_original_metadata,
        )
        return err

    for op in operations:
        try:
            resolved_op = _resolve_stable_to_span(op, tree)
        except StaleNodeIdError as _stale:
            return _rollback_and_fail(
                error_result_for_edit(
                    str(_stale),
                    "STALE_NODE_ID",
                    {
                        "field": _stale.field,
                        "stable_id": _stale.stable_id,
                        "hint": (
                            "Call universal_file_preview (with session_id) "
                            "after each edit to refresh node_ref values "
                            "before the next operation."
                        ),
                    },
                )
            )
        try:
            normalized_op = _normalized_cst_modify_operation(resolved_op)
        except ValueError as exc:
            return _rollback_and_fail(
                error_result_for_edit(
                    str(exc),
                    "INVALID_OPERATION",
                    {"operation": op},
                )
            )
        built, err = build_tree_operations(tree, [normalized_op])
        if err is not None:
            return _rollback_and_fail(err)
        if not built:
            return _rollback_and_fail(
                error_result_for_edit(
                    "No operations built from edit payload",
                    "INVALID_OPERATION",
                    {"operation": normalized_op},
                )
            )
        try:
            tree = modify_tree(tree.tree_id, built)
        except ValueError as exc:
            return _rollback_and_fail(
                error_result_for_edit(
                    str(exc),
                    "INVALID_OPERATION",
                    {"operation": op},
                )
            )
        session.tree_id = tree.tree_id
        try:
            write_sidecar_atomic(session.abs_path, tree)
        except Exception as exc:
            return _rollback_and_fail(
                error_result_for_edit(
                    str(exc),
                    "WRITE_FAILED",
                    {"path": str(session.abs_path)},
                )
            )

    return SuccessResult(data={"success": True, "updated": True})
