"""
NavigationProcedure (C-006) for universal_file_preview.

Single three-phase function shared by all NodeKind values and all file
types: enumerate the focus node's block set, select a subset via
Selector (C-007), render each selected block via BlockHandler (C-008).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base_handler import FileHandler
from .block_handlers import render_block
from .budget import PreviewBudget
from .errors import (
    INPUT_ERROR_CONFLICTING_PARAMETERS,
    PreviewError,
    input_error,
)
from .models import Block, NavigationResult, Node
from .selector import apply_selector
from .session import resolve_session
from .node_ref_params import normalize_optional_node_ref
from .marked_tree_navigation import (
    navigate_degraded_as_text,
    navigate_marked_tree,
    normalize_marked_tree_node_ref,
    resolve_session_pointer_node_ref,
    should_use_marked_tree_navigation,
)

_PYTHON_EXTENSIONS = frozenset({".py", ".pyi", ".pyw"})


def navigate(
    handler: FileHandler,
    params: dict[str, Any],
    budget: PreviewBudget,
) -> NavigationResult | PreviewError:
    """
    Execute the three-phase NavigationProcedure (C-006) for one request.

    Phase 1 — enumerate: produce the focus node's ordered block set.
    Phase 2 — select: apply Selector (C-007) to the block set.
    Phase 3 — render: invoke BlockHandler (C-008) for each selected block.

    Args:
        handler: FileHandler resolved by HandlerDispatcher for the file.
        params: Validated parameter dict containing keys:
                'file_path' (str), 'node_ref' (str|int|None),
                'selector' (str|list|None), 'project_id' (str),
                'tree_id' (str|None).
        budget: PreviewBudget with preview_lines and value_preview_len.

    Returns:
        NavigationResult on success, or PreviewError on failure.
    """
    marked_params = dict(params)
    resolve_session_pointer_node_ref(marked_params)
    if should_use_marked_tree_navigation(handler, marked_params):
        norm_err = normalize_marked_tree_node_ref(marked_params)
        if norm_err is not None:
            return norm_err
        return navigate_marked_tree(marked_params, budget)

    ext = Path(str(params.get("file_path", ""))).suffix.lower()
    if ext in _PYTHON_EXTENSIONS:
        return input_error(
            INPUT_ERROR_CONFLICTING_PARAMETERS,
            "Python preview requires project_id (marked-tree navigation only).",
            details={"file_path": params.get("file_path")},
        )

    session_result = resolve_session(handler, params)
    if isinstance(session_result, PreviewError):
        return session_result
    session, session_origin, tree_id = session_result

    preview_budget = params.get("preview_budget") or budget
    open_result = handler.open_root(params["file_path"], session, budget=preview_budget)
    if isinstance(open_result, PreviewError):
        return open_result
    focus_node: Node = open_result
    if focus_node.is_invalid:
        parse_err = (focus_node.attributes or {}).get("parse_error", "parse error")
        return navigate_degraded_as_text(
            params,
            budget,
            parse_error=str(parse_err),
        )
    node_ref_raw = normalize_optional_node_ref(params.get("node_ref"))
    if node_ref_raw is not None and not focus_node.is_invalid:
        resolve_result = handler.resolve_node_ref(node_ref_raw, session)
        if isinstance(resolve_result, PreviewError):
            return resolve_result
        focus_node = resolve_result

    block_set: list[Node] = focus_node.children
    total_blocks = len(block_set)

    selector_result = apply_selector(
        params.get("selector"), block_set, budget.preview_lines
    )
    if isinstance(selector_result, PreviewError):
        return selector_result
    selected_nodes = selector_result

    selected_blocks: list[Block] = []
    for node in selected_nodes:
        summary = render_block(node, budget.value_preview_len)
        raw_text = (node.attributes or {}).get("text")
        block_text = raw_text if isinstance(raw_text, str) else None
        selected_blocks.append(
            Block(
                node_kind=node.node_kind,
                node_ref=node.node_ref,
                summary=summary,
                text=block_text,
            )
        )

    return NavigationResult(
        focus_node=focus_node,
        total_blocks=total_blocks,
        selected_blocks=selected_blocks,
        tree_id=tree_id if session_origin == "command_created" else None,
    )
