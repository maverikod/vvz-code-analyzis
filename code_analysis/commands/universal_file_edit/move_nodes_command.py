"""
universal_file_move_nodes command: move a contiguous list of sibling CST nodes
to a new position within the same file edit session.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.errors import (
    SESSION_NOT_FOUND,
    PARSE_ERROR,
    WRITE_FAILED,
    error_result_for_edit,
    error_result_from_make_error,
    make_error,
)
from code_analysis.commands.universal_file_edit.format_group import FORMAT_SIDECAR
from code_analysis.commands.universal_file_edit.session import EditSession, get_session
from code_analysis.core.cst_tree.models import CSTTree, TreeOperation, TreeOperationType
from code_analysis.core.cst_tree.node_stable_id import logical_source_from_module
from code_analysis.core.cst_tree.tree_builder import (
    _build_tree_index,
    get_tree,
    load_file_to_tree,
    rollback_tree_to_code,
)
from code_analysis.core.cst_tree.tree_modifier import modify_tree
from code_analysis.core.cst_tree.tree_sidecar import write_sidecar_atomic
from code_analysis.core.cst_tree.models import ROOT_NODE_ID_SENTINEL


def _validate_python_source(source: str, filename: str) -> Optional[str]:
    """Compile source via Python's built-in compiler. Returns error string or None."""
    try:
        compile(source, filename, "exec")
        return None
    except SyntaxError as exc:
        return f"SyntaxError at line {exc.lineno}: {exc.msg}"
    except Exception as exc:
        return str(exc)


def _sorted_node_ids_by_tree_order(tree: CSTTree, node_ids: List[str]) -> List[str]:
    """Return node_ids sorted by their start_line in the tree (source order)."""

    def _line(nid: str) -> int:
        meta = tree.metadata_map.get(nid)
        return meta.start_line if meta else 0

    return sorted(node_ids, key=_line)


def _run_sidecar_move_batch(
    session: EditSession,
    source_node_ids: List[str],
    target_node_id: Optional[str],
    parent_node_id: Optional[str],
    position: str,
) -> SuccessResult | ErrorResult:
    """Apply move as DELETE + INSERT synchronously (called via asyncio.to_thread).

    Strategy:
    1. Remember the source text of each node (before any mutation).
    2. Build DELETE ops for all source nodes.
    3. Build a single INSERT op with the combined remembered text.
    4. Apply all ops in one modify_tree call; stable_id is restored
       automatically by _apply_single_op via extract/restore_stable_data.
    5. Export result to a temp .py file and validate via compile().
    6. OK  -> delete temp file, update session tree, write sidecar.
       FAIL -> delete temp file, rollback tree, return error.
    """
    # --- Resolve tree ---
    tid = session.tree_id
    tree = get_tree(tid) if tid else None
    if tree is None:
        try:
            tree = load_file_to_tree(str(session.abs_path))
        except FileNotFoundError as exc:
            return error_result_for_edit(
                str(exc), "FILE_NOT_FOUND", {"path": str(session.abs_path)}
            )
        except Exception as exc:
            return error_result_for_edit(
                str(exc), PARSE_ERROR, {"path": str(session.abs_path)}
            )
    session.tree_id = tree.tree_id

    # --- Snapshot for rollback ---
    original_code = logical_source_from_module(tree.module)
    original_tree_id = tree.tree_id
    original_metadata = dict(tree.metadata_map)

    def _rollback() -> None:
        rollback_tree_to_code(
            original_tree_id,
            original_code,
            index_metadata_for_code=original_metadata,
        )
        session.tree_id = original_tree_id
        restored = get_tree(original_tree_id)
        if restored is not None:
            write_sidecar_atomic(session.abs_path, restored)

    def _rollback_and_fail(err: ErrorResult) -> ErrorResult:
        _rollback()
        return err

    # --- Predcheck: all source_node_ids exist ---
    for nid in source_node_ids:
        if nid not in tree.metadata_map:
            return error_result_for_edit(
                f"Node not found: {nid}",
                "STALE_NODE_ID",
                {
                    "stable_id": nid,
                    "hint": "Re-call universal_file_preview with session_id.",
                },
            )

    # --- Sort source nodes by tree order (top-to-bottom) ---
    ordered_ids = _sorted_node_ids_by_tree_order(tree, source_node_ids)

    # --- Step 1: remember the source text of each node BEFORE any mutation ---
    node_codes: List[str] = []
    for nid in ordered_ids:
        node = tree.node_map.get(nid)
        if node is None:
            return error_result_for_edit(
                f"Node object not found for id: {nid}",
                "STALE_NODE_ID",
                {"stable_id": nid},
            )
        node_codes.append(tree.module.code_for_node(node))

    # --- Step 2: build DELETE ops for all source nodes ---
    ops: List[TreeOperation] = [
        TreeOperation(action=TreeOperationType.DELETE, node_id=nid)
        for nid in ordered_ids
    ]

    # --- Step 3: build a single INSERT op with the combined remembered code ---
    combined_code = "".join(node_codes)
    if target_node_id is not None:
        insert_op = TreeOperation(
            action=TreeOperationType.INSERT,
            target_node_id=target_node_id,
            position=position,
            code=combined_code,
        )
    else:
        insert_op = TreeOperation(
            action=TreeOperationType.INSERT,
            parent_node_id=parent_node_id or ROOT_NODE_ID_SENTINEL,
            position=position,
            code=combined_code,
        )
    ops.append(insert_op)

    # --- Step 4: apply via modify_tree ---
    try:
        tree = modify_tree(tree.tree_id, ops)
    except ValueError as exc:
        return _rollback_and_fail(
            error_result_for_edit(
                str(exc), "INVALID_OPERATION", {"source_node_ids": source_node_ids}
            )
        )
    except Exception as exc:
        return _rollback_and_fail(
            error_result_for_edit(
                str(exc), "INVALID_OPERATION", {"source_node_ids": source_node_ids}
            )
        )

    session.tree_id = tree.tree_id

    # --- Step 5: validate via temp file + compile() ---
    # Temp file lives next to source (same FS). Removed in finally regardless of outcome.
    tmp_path = session.abs_path.with_suffix(".py.tmp")
    try:
        result_source = logical_source_from_module(tree.module)
        tmp_path.write_text(result_source, encoding="utf-8")
        syntax_error = _validate_python_source(result_source, str(tmp_path))
        if syntax_error is not None:
            return _rollback_and_fail(
                error_result_for_edit(
                    f"Move produced invalid Python: {syntax_error}",
                    "INVALID_OPERATION",
                    {"syntax_error": syntax_error, "source_node_ids": source_node_ids},
                )
            )
    except Exception as exc:
        return _rollback_and_fail(
            error_result_for_edit(str(exc), WRITE_FAILED, {"path": str(tmp_path)})
        )
    finally:
        # Temp file used only for validation — always remove.
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    # --- Step 6: validation passed — write sidecar (draft only, .py unchanged) ---
    try:
        write_sidecar_atomic(session.abs_path, tree)
    except Exception as exc:
        return _rollback_and_fail(
            error_result_for_edit(
                str(exc), WRITE_FAILED, {"path": str(session.abs_path)}
            )
        )

    return SuccessResult(
        data={"success": True, "updated": True, "moved": len(ordered_ids)}
    )


class UniversalFileMoveNodesCommand(BaseMCPCommand):
    """MCP command: move a contiguous sibling block of CST nodes to a new position.

    Works within an open universal_file_edit session (sidecar/Python only).
    Mutates only the in-memory draft tree; source file on disk is unchanged
    until universal_file_write (commit).
    """

    name = "universal_file_move_nodes"
    version = "1.0.0"
    descr = "Move a contiguous block of sibling CST nodes to a new position in the same file session."
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID. Use list_projects to discover valid values.",
                },
                "session_id": {
                    "type": "string",
                    "description": "Active session UUID returned by universal_file_open.",
                },
                "source_node_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": (
                        "Stable UUIDs of nodes to move. Must all be siblings in the current "
                        "draft tree (same parent). Order from the caller is ignored; nodes "
                        "are moved in source-order as found in the tree."
                    ),
                },
                "target_node_id": {
                    "type": "string",
                    "description": (
                        "Sibling-relative anchor: insert block before or after this node. "
                        "Mutually exclusive with parent_node_id."
                    ),
                },
                "parent_node_id": {
                    "type": "string",
                    "description": (
                        "Container anchor: insert block as first or last child of this node. "
                        "Use __root__ for module level. Mutually exclusive with target_node_id."
                    ),
                },
                "position": {
                    "type": "string",
                    "enum": ["before", "after", "first", "last"],
                    "description": (
                        "Insertion position. With target_node_id: before|after. "
                        "With parent_node_id: first|last."
                    ),
                    "default": "after",
                },
            },
            "required": ["project_id", "session_id", "source_node_ids"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        session_id: str,
        source_node_ids: List[str],
        target_node_id: Optional[str] = None,
        parent_node_id: Optional[str] = None,
        position: str = "after",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute move_nodes on the session draft."""
        del project_id, kwargs

        # Validate that exactly one anchor is given.
        if target_node_id is not None and parent_node_id is not None:
            return error_result_from_make_error(
                make_error(
                    "INVALID_OPERATION",
                    "Provide either target_node_id or parent_node_id, not both.",
                )
            )
        if target_node_id is None and parent_node_id is None:
            # Default: module root, last position.
            parent_node_id = ROOT_NODE_ID_SENTINEL
            position = "last"

        try:
            session = get_session(session_id)
        except ValueError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
            )

        if session.format_group != FORMAT_SIDECAR:
            return error_result_from_make_error(
                make_error(
                    "INVALID_OPERATION",
                    "universal_file_move_nodes only supports Python (.py) sidecar sessions.",
                )
            )

        return await asyncio.to_thread(
            _run_sidecar_move_batch,
            session,
            source_node_ids,
            target_node_id,
            parent_node_id,
            position,
        )
